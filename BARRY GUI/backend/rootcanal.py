# -*- coding: utf-8 -*-
"""rootcanal.py -- taking the hidden IEDs out of a dentate spike set.

Step four of The Dentist, between Braces and X-ray:

    Incisor (find them) -> Checkup (clean them) -> Braces (line them up)
      -> Root Canal (take the IEDs out) -> X-ray (tell them apart)

WHY THIS STEP EXISTS
====================
Incisor's detector finds large, fast, depth-specific deflections in the
hilus. So does an interictal discharge. Nothing in Checkup or Braces asks
which of the two an event is -- Checkup asks "is this a real event", Braces
asks "where exactly is it" -- so on an epileptic animal the aligned DS set
arrives at X-ray with IEDs in it, and X-ray then splits DS1 from DS2 on a
population that is partly neither.

The lab settled how to tell them apart in `FOOOF Playgroun/IED and such`
(`ied_ampwidth.py`, `ied_ds_features.py`, `ied_ampwidth_gui_v5.py`,
`ied_ds_lit.py`), on the very recording used to test this one (PTEN m13 s2,
2023-08-01). Three numbers per event, decided with the user and NOT settings
here:

  1. MAX AMPLITUDE (uV), on the max-amp contact. Per event, the good contact
     with the largest |x - baseline| inside +-`win_ms` of the stamp, where the
     baseline for the pick is that contact's median over the whole snippet
     (v4's `winning_contact`). On that contact, v1's `measure_peak`: a real
     local baseline (the median of the 30-60 ms flanks either side), both
     polarities measured, the larger one taken.
  2. HALF-WIDTH (ms), full width at half that amplitude, from the same
     baseline, on the same contact, crossings linearly interpolated. A
     crossing the search (+-50 ms) never finds is NaN -- `unresolved` --
     never the window edge dressed up as a width.
  3. HF POWER (dB), v5's measure: Welch PSD, band power by trapezoid, event
     window +-25 ms, baseline +-20 ms centred 150 ms before on the same
     contact, 10*log10(event/baseline); per event the best contact's dB
     (nanmax across good contacts, v5's `best_db`). The one departure from
     v5, asked for by the user: the BAND IS A SETTING (default 500-1000 Hz,
     up to the read's Nyquist), so it is carried in every result and in the
     axis label. Two runs over different bands are different measurements,
     and nothing in the numbers alone would say so.

Each axis is z-scored per recording and a 2-class k-means runs on the three.
The cluster whose centre has the higher HF power in dB (unscaled) is called
IED. An event missing any of the three (an unresolved half-width, a missed
HF window) is left out of the clustering and reported as not measured. It is
never imputed, because an imputed IED would be a guess wearing a number.

READ ONCE, FIT MANY TIMES
=========================
The same split X-ray makes. `read` is minutes: every event, every contact,
off the disk at 5 kHz (`incisor.decimation_for` + `incisor._decimate`, what
`dspcahf.measure` does). It keeps two things per event per contact:

  * a +-250 ms waveform snippet, taken down again to 2 kHz, so any filter up
    to a 400 Hz lowpass can be applied later without reading again. Stored
    as float16 microvolts, with each snippet's median taken off first and
    kept beside it as float32, so the half-precision step is set by the
    event's own size rather than by the amplifier's offset.
  * the event-window and baseline-window PSDs at 5 kHz, so any band up to
    2000 Hz -- the decimation filter's corner, see DECIMATE_CORNER -- is a
    trapezoid over numbers already on disk.

`fit` is everything else, from those arrays: filter, pick the contact,
measure, integrate the band, z-score, k-means, name, apply the overrides.
Changing the filter, the band, the window, a flip or a centre is a fit and
never touches the recording.

READ IN MERGED SPANS, CHANNEL BY CHANNEL
========================================
`dspcahf.measure` opens every channel once per event, which on this recording
is 296 x 64 = 18,944 reads. Here the stamps are merged into spans first
(`braces.spans`, as X-ray's read does -- events closer than a second share a
read), and the loop runs channel-outer, span-inner, so each .ncs file is
walked forwards once instead of being revisited 177 times in between reads
of the other 63. Measured on this machine's copy of 46fd29a77cc7, the
channel-major order read 320 windows in 1.8 s against 3.5 s span-major.
The whole read of that set -- 296 events in 177 spans, 64 channels, off
local D: -- took 106 s, plus 4.5 s for the bad-contact screen, and files an
.npz of 51 MB. The arithmetic of which sample is which stamp's is done per channel, off that
channel's own first-sample time, so merging cannot shift an event.

WHAT A 500 MS SNIPPET DOES TO A 1 HZ HIGH-PASS, MEASURED
=======================================================
A 1 Hz high-pass has a time constant of about 160 ms; on a 500 ms snippet it
cannot mean what it means on continuous data, and the spec asked for the size
of the difference rather than an assumption about it. So the same measure --
max-amp contact, amplitude and half-width at the default 1-100 Hz, +-25 ms --
was taken twice on real events of 46fd29a77cc7: once exactly as `fit` does it
(the stored +-250 ms, 2 kHz snippet, filtered on its own) and once on a
+-5 s continuous read of the same contact, filtered whole and then cut to the
same +-250 ms. Measured 2026-09-25, 24 events every 12th through the set
(median amplitude ~1.8 mV, median half-width 24.7 ms):

    contact picked      the same on 24 of 24
    amplitude           median |diff| 0.50 %,  worst 2.5 %
    half-width          median |diff| 0.074 ms (0.28 %),  worst 0.33 ms (1.6 %)

That is WITH the filter padded by an even extension a snippet long (see
`_filter`). Scipy's default padding -- 27 samples of odd extension -- was
measured first on 12 of those events and is what that choice rests on:

    default (odd, 27)   same contact 9/12, amplitude worst 24 %, half-width
                        worst 8.2 ms (median 1.2 % and 0.12 ms)
    odd, a snippet long same contact 11/12, amplitude worst 2.5 %,
                        half-width worst 0.79 ms
    detrend, then odd   no better than odd alone
    even, a snippet long same contact 12/12, amplitude worst 1.1 %,
                        half-width worst 0.26 ms

So the snippet stands in for the continuous trace to about half a percent
on a typical event and a few percent at worst. Where it disagrees, it is the
1 Hz high-pass settling differently near the snippet's edges; a corner at
0 Hz (lowpass only) removes that difference entirely, at the price of
leaving the slow field in.

THE HF NUMBER IS dspcahf's. Checked against `dspcahf.measure` (X-ray's
second read, which reads one window per event) on 4 of those events and
all 62 good contacts: median |diff| 0.00 dB, worst 0.05 dB, and each
event's best-contact dB to within 0.03 dB. The difference is the
decimation's edge landing in a different place when neighbouring stamps
share a span.

NOTHING HERE DRAWS. No matplotlib, at any depth, for the reason `dspca.py`
gives: the browser draws, from arrays, and a figure is filed from the canvas
somebody actually looked at.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction

import numpy as np

from . import braces, csc, dspca, dspcahf, incisor

# Loaded on first use, not at start-up; see lazyimp.py for why.
from . import lazyimp  # noqa: E402
HAVE_SCIPY = lazyimp.have("scipy")
if HAVE_SCIPY:
    butter, resample_poly, sosfiltfilt = lazyimp.names(
        "scipy.signal", "butter", "resample_poly", "sosfiltfilt")
else:
    butter = resample_poly = sosfiltfilt = None

# Guarded for the reason `dspca.py` gives: `app.py` imports every backend
# module at boot, and a machine without scikit-learn must lose one tool, not
# the server.
HAVE_SKLEARN = lazyimp.have("sklearn")
KMeans = (lazyimp.names("sklearn.cluster", "KMeans")
          if HAVE_SKLEARN else None)


class RootCanalError(Exception):
    """Something a person can fix, said in a sentence."""


# --------------------------------------------------------------------------
# The numbers
# --------------------------------------------------------------------------
# The read. Changing any of these changes what is on disk.
READ_FS = dspcahf.HF_FS          # 5 kHz: the PSDs are taken at this rate
SNIP_FS = 2000.0                 # the waveform snippet, after a second step
SNIP_MS = 250.0                  # +- around the stamp
HF_WIN_MS = dspcahf.HF_WIN_MS            # +-25 ms event window (v5)
HF_BASE_OFF_MS = dspcahf.HF_BASE_OFF_MS  # baseline centred 150 ms before
HF_BASE_WIN_MS = dspcahf.HF_BASE_WIN_MS  # and 40 ms wide
PAD_S = dspcahf.HF_PAD_S         # margin read and thrown away, per span
MERGE_GAP_S = 1.0                # stamps closer than this share a read

# The fit. Defaults, every one of them a setting.
LO_HZ, HI_HZ = 1.0, 100.0        # the amplitude/half-width filter
FILTER_ORDER = 4                 # Butterworth, zero-phase (sosfiltfilt)

# WHICH FILTER THE AMPLITUDE AND HALF-WIDTH ARE MEASURED ON, as a choice of
# four, asked for by the user (2026-10-01) once it was clear the default had
# been a recommendation rather than a measurement.
#
#   none    the stored 2 kHz snippet as it is. Nothing taken out -- mains
#           included -- which is the point of having it: the baseline every
#           other choice is a change from.
#   ds      the dentate-spike filter. Toothy's 5-100 Hz detection band at
#           its own order (the band Incisor found these events on, and X-ray
#           measures them on), with the 60 Hz mains FITTED out the way the
#           CSD's is (`_line_out`). The whole Dentist on one waveform.
#   lfp     1-100 Hz, order 4: the LFP / morphology band `ied_ds_lit.py`
#           takes from the epilepsy literature, and this tool's default
#           since it was built. No mains removal -- that is the literature
#           band as it is used -- and on PTEN m1 s2 it left 23 of 64 events
#           measured on CSC41, a contact carrying heavy mains as well as
#           real events. Kept the default so that nothing already fitted
#           changes under anyone; choosing another is one click.
#   custom  the corners and order given, with the mains out or not.
#
# A preset FIXES its corners and order: a "ds" fit with lo_hz 3 would be two
# different filters under one name, so a preset's numbers are its own and
# whatever came with the request is ignored.
FILTERS = {
    "none": {"lo_hz": 0.0, "hi_hz": 0.0, "order": 0, "mains_out": False,
             "label": "no filter"},
    "ds": {"lo_hz": float(incisor.DS_BAND[0]), "hi_hz": float(incisor.DS_BAND[1]),
           "order": int(incisor.DS_ORDER), "mains_out": True,
           "label": "DS filter"},
    "lfp": {"lo_hz": LO_HZ, "hi_hz": HI_HZ, "order": FILTER_ORDER,
            "mains_out": False, "label": "LFP filter"},
}
FILTER_KINDS = ("none", "ds", "lfp", "custom")
DEFAULT_FILTER = "lfp"

# HOW MANY CLUSTERS. 1 to 6, asked for by the user on 2026-10-02. Two is what
# the tool was built on and stays the default; one is no split at all, which
# is the honest null to compare a split against.
K_MIN, K_MAX, K_DEFAULT = 1, 6, 2
WIN_MS = 25.0                    # +- where the contact and the peak are picked
BAND = (500.0, 1000.0)           # the HF band (v5's), now adjustable

# WHERE THE BAND HAS TO STOP, MEASURED: 2000 Hz, NOT THE 2500 Hz NYQUIST.
#
# The read goes 30 kHz -> 5 kHz through `scipy.signal.decimate`'s IIR, a
# Chebyshev I whose corner sits at 0.8 of the NEW Nyquist -- 2000 Hz. Below
# that corner the 5 kHz read is the raw signal; above it the signal is being
# cut and a band there reads power the filter took away.
#
# Checked against the raw 30 kHz on 24 real events of PTEN m13 s2, same
# contact, same windows, v5's measure, the Welch segment matched to the
# window at both rates:
#
#     500-1000 Hz    worst |diff| 0.09 dB   r 1.000
#    1000-1500 Hz    worst |diff| 0.16 dB   r 1.000
#    1500-2000 Hz    worst |diff| 0.27 dB   r 1.000
#    2000-2500 Hz    worst |diff| 9.51 dB   r 0.831   <- past the corner
#
# So the rate is not what limits this measurement below 2 kHz, and it is
# exactly what limits it above.
#
# ONE THING THAT DOES DEPEND ON THE RATE, and it is v5's rule, not the
# decimation. `nperseg` is "the window or 512 samples, whichever is
# smaller" -- counted in SAMPLES. At 5 kHz the 50 ms window is 251 samples
# and is one Welch segment; at 30 kHz it is 1501 and is split into 17 ms
# segments and averaged. For a transient sitting in the middle of the window
# those are different estimators: run on the raw file with that rule, the
# same events read a median 2.2 dB LOWER (r 0.98). v5 itself reads at 5 kHz
# (HF_Q = 6), so at 5 kHz this is v5's number; a raw-rate "v5" would not be.
DECIMATE_CORNER = 0.8            # scipy.signal.decimate's IIR corner / Nyquist
CROSS_MS = 50.0                  # +- where the half-amplitude crossings are
V1_CROSS_MS = 50.0               # v1's own search, which `wide` is measured
                                 # against whatever the setting is
CROSS_MS_RANGE = (10.0, 200.0)   # what the setting may be
CROSS_EDGE_MS = 50.0             # how far inside the snippet's edge the
                                 # search must stop -- see `_check_cross`
                                 # hunted (v4's `event_features`)
FLANK_MS = (30.0, 60.0)          # the local baseline's flanks (v1)
SEED = 0
N_INIT = 10

# The ceiling on the lowpass. The snippet is at 2 kHz; above about a fifth
# of that the stored trace has already been shaped by the anti-alias filter
# of the 5 kHz -> 2 kHz step, and a filter placed there would be measuring
# that filter rather than the event.
MAX_HI_HZ = 400.0
# The display cap the panel asked for: no array in time longer than this.
MAX_POINTS = 400
DISPLAY_MS = 100.0

AXES = ("amp_uV", "hw_ms", "hf_db")

# Two job stages of Root Canal's own. Registered into `cfc.STAGES` by
# `register_stages`, for the reason that list gives about every other tool:
# a rate is seconds per unit, and a stage name shared with X-ray's read
# (windows) or its batch would teach both tools the wrong one.
STAGE_READ = "root canal read"
STAGE_SETS = "root canal sets"
_STAGES = ((STAGE_READ, "channels", 1.2), (STAGE_SETS, "recordings", 90.0))


def register_stages(cfcmod):
    """Declare this tool's job stages to the job machinery. Idempotent.

    `cfc.Job` keeps only the stages its STAGES list names -- anything else is
    dropped without a word, which is a run that works and shows no progress
    (`dspcahf`'s own "ds pca hf" is in exactly that state). Called by
    `app.py` before `cfc.configure`, so a rate this machine has measured for
    them is kept across restarts rather than thrown away as unrecognised.

    Flat: the unit already carries the size of the job (a channel read over
    every event's span; a whole recording), so the per-megasample scaling
    would count it twice.
    """
    have = {name for name, _unit in cfcmod.STAGES}
    for name, unit, seed in _STAGES:
        if name not in have:
            cfcmod.STAGES.append((name, unit))
        cfcmod._RATES.setdefault(name, seed)
        cfcmod._FLAT.add(name)


def stamps_hash(stamps):
    """A name for a list of stamp times, at curation's own resolution.

    Content rather than a version label, because one list of stamps has more
    than one name: the live set and the version it was banked as are the
    same stamps, and a batch that read the live set must be found again by a
    panel that asks for it by version.
    """
    ts = sorted(round(float(e["t"] if isinstance(e, dict) else e), 4)
                for e in stamps or [])
    blob = json.dumps(ts, separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


class Params:
    """One question, as an attribute bag, split the way every Jarvis tool is.

    `READ_KEYS` change what comes off the disk; `FIT_KEYS` change only what
    is done with it afterwards. The read cache is keyed on the first group
    alone, so no fit setting -- filter, band, window, a flip, a dragged
    centre -- can cost a re-read.

    `from_version` is carried and recorded but is NOT in the read key. The
    stamps hash is: it is the content the version label is a name for, and
    the live set and "v3" are one list of stamps under two names. Keyed on the
    label, a batch that read the live set was invisible to a panel that asked
    for v3 and the recording was read twice.

    Nothing about the RECORDING is in the read key either -- not the
    polarity, not the probe, not which contacts are marked bad -- because a
    fit has to find its read from the bank alone, without opening a
    recording that may not be on this machine. Those are carried inside the
    read instead, and the read route re-reads when the marked-bad list it was
    filed with no longer matches (see `_rootcanal_is_read` in app.py).
    """

    READ_KEYS = ("entry_id", "stamps_hash", "read_fs", "snip_fs", "snip_ms",
                 "hf_win_ms", "hf_base_off_ms", "hf_base_win_ms", "pad_s")
    FIT_KEYS = ("filt", "mains_out", "lo_hz", "hi_hz", "order", "win_ms",
                "band_lo", "band_hi", "cross_ms", "flank_ms", "seed", "n_init",
                "flips", "centres", "k", "cluster_calls", "margin",
                "complete_only", "drawn", "retry", "cluster_names")

    def __init__(self, **kw):
        g = kw.get
        # -- the read -------------------------------------------------
        self.entry_id = g("entry_id")
        self.from_version = g("from_version")
        self.stamps_hash = g("stamps_hash")
        self.read_fs = float(g("read_fs") or READ_FS)
        self.snip_fs = float(g("snip_fs") or SNIP_FS)
        self.snip_ms = float(g("snip_ms") or SNIP_MS)
        self.hf_win_ms = float(g("hf_win_ms") or HF_WIN_MS)
        self.hf_base_off_ms = float(g("hf_base_off_ms") or HF_BASE_OFF_MS)
        self.hf_base_win_ms = float(g("hf_base_win_ms") or HF_BASE_WIN_MS)
        self.pad_s = float(g("pad_s") if g("pad_s") is not None else PAD_S)
        self.invert = bool(g("invert", True))
        # Facts about the recording the read carries, not part of its name:
        # which probe (for the CSD's columns) and at what pitch.
        self.probe = g("probe") or None
        self.spacing = g("spacing")

        # -- the fit --------------------------------------------------
        self.filt = str(g("filt") or DEFAULT_FILTER).strip().lower()
        if self.filt not in FILTER_KINDS:
            raise RootCanalError(
                "The filter has to be one of %s, not %r."
                % (", ".join(FILTER_KINDS), self.filt))
        if self.filt in FILTERS:
            pre = FILTERS[self.filt]
            self.lo_hz, self.hi_hz = pre["lo_hz"], pre["hi_hz"]
            self.order, self.mains_out = pre["order"], pre["mains_out"]
        else:
            self.lo_hz = _num(g("lo_hz"), LO_HZ, "the filter's low corner")
            self.hi_hz = _num(g("hi_hz"), HI_HZ, "the filter's high corner")
            self.order = int(_num(g("order"), FILTER_ORDER,
                                  "the filter order"))
            mo = g("mains_out")
            self.mains_out = True if mo is None else bool(mo)
        self.win_ms = _num(g("win_ms"), WIN_MS, "the amplitude window")
        self.band_lo = _num(g("band_lo"), BAND[0], "the band's low edge")
        self.band_hi = _num(g("band_hi"), BAND[1], "the band's high edge")
        self.cross_ms = _num(g("cross_ms"), CROSS_MS, "the crossing search")
        fl = g("flank_ms") or FLANK_MS
        self.flank_ms = [float(fl[0]), float(fl[1])]
        self.seed = int(_num(g("seed"), SEED, "the seed"))
        self.n_init = max(10, int(_num(g("n_init"), N_INIT, "n_init")))
        # HOW MANY CLUSTERS, 1 to 6 (asked for 2026-10-02). Two is what
        # this tool was built on and stays the default.
        # Events missing an axis left out of the clustering altogether,
        # rather than placed on the two they have -- Pooled's switch, here
        # too, so the two views take the same settings.
        self.complete_only = bool(g("complete_only", False))
        # CLUSTERS DRAWN BY HAND: [{"events": [i, ...], "call": "ds"|"ied"}].
        # Their events are held out of k-means and form clusters of their
        # own, after its k, with the call given. Kept as fit params so a
        # result with a drawn cluster rebuilds from params alone.
        self.drawn = []
        seen = set()
        for grp in (g("drawn") or []):
            try:
                evs = sorted({int(i) for i in (grp or {}).get("events") or []})
            except (TypeError, ValueError):
                raise RootCanalError("A drawn cluster is a list of event "
                                     "numbers and a call.")
            call = str((grp or {}).get("call") or "").lower()
            if call not in ("ds", "ied"):
                raise RootCanalError("A drawn cluster is called DS or IED, "
                                     "not %r." % (call,))
            if not evs:
                continue
            if seen & set(evs):
                raise RootCanalError(
                    "An event is in two drawn clusters (%s); draw it into "
                    "one." % ", ".join(str(i + 1)
                                       for i in sorted(seen & set(evs))[:5]))
            seen |= set(evs)
            self.drawn.append({"events": evs, "call": call})
        kk = _num(g("k"), K_DEFAULT, "the number of clusters")
        if kk != int(kk) or not K_MIN <= int(kk) <= K_MAX:
            raise RootCanalError(
                "The number of clusters has to be a whole number from %d to "
                "%d, not %s." % (K_MIN, K_MAX, _g(kk)))
        self.k = int(kk)
        # Calls given by hand, by cluster rank: {"<rank>": "ds" | "ied"}.
        cc = g("cluster_calls") or {}
        if not isinstance(cc, dict):
            raise RootCanalError(
                "Cluster relabels have to be {cluster: \"ds\" or \"ied\"}.")
        self.cluster_calls = {}
        for key, v in cc.items():
            try:
                r = int(key)
            except (TypeError, ValueError):
                raise RootCanalError("A cluster is named by its number, not "
                                     "%r." % (key,))
            v = str(v or "").strip().lower()
            if v not in ("ds", "ied"):
                raise RootCanalError("A cluster can be called DS or IED, not "
                                     "%r." % (v,))
            self.cluster_calls[str(r)] = v
        # A saved margin to apply, by reference. The app resolves it to its
        # payload; Params only carries what was asked for, so the request
        # can be rebuilt from params alone.
        mg = g("margin")
        if mg in (None, "", {}):
            self.margin = None
        else:
            if not isinstance(mg, dict) or not mg.get("artifact_id"):
                raise RootCanalError(
                    "A margin is named by its artifact id (and optionally a "
                    "version and a mode).")
            mode = str(mg.get("mode") or "fixed").lower()
            if mode not in ("fixed", "refine"):
                raise RootCanalError("A margin is applied fixed or refined, "
                                     "not %r." % (mode,))
            self.margin = {"artifact_id": str(mg["artifact_id"]),
                           "version": mg.get("version"), "mode": mode}
        try:
            self.flips = sorted({int(i) for i in (g("flips") or [])})
        except (TypeError, ValueError):
            raise RootCanalError(
                "The hand-flipped events have to be a list of event numbers.")
        # CLUSTER NAMES (2026-10-06): {"<rank>": {"name", "type"}}, from the
        # lab's list or typed. The type is DS or IED and IS the cluster's
        # call -- a name says what a cluster is -- so a named cluster is
        # called by its name, over the rule and a hand relabel. A fit param,
        # so a named result rebuilds from params alone.
        nm = g("cluster_names") or {}
        if not isinstance(nm, dict):
            raise RootCanalError(
                "Cluster names have to be {cluster: {name, type}}.")
        self.cluster_names = {}
        for key, v in nm.items():
            try:
                r = int(key)
            except (TypeError, ValueError):
                raise RootCanalError("A cluster is named by its number, not "
                                     "%r." % (key,))
            v = v or {}
            name = str(v.get("name") or "").strip()
            typ = str(v.get("type") or "").strip().lower()
            if not name:
                continue
            if len(name) > 60:
                raise RootCanalError("A cluster name is a name: keep it under "
                                     "60 characters, not %d." % len(name))
            if typ not in ("ds", "ied"):
                raise RootCanalError("A cluster name is a DS name or an IED "
                                     "name, not %r." % (typ,))
            self.cluster_names[str(r)] = {"name": name, "type": typ}
        # EVENTS WHOSE HALF-WIDTH WAS NOT FOUND, SEARCHED AGAIN ON REQUEST.
        # Each one is measured once more with the widest search the stored
        # snippet allows (`retry_cross_ms`) -- only those events, so the
        # rest keep the search everyone else was measured with. A fit
        # param, so a result with retries rebuilds from params alone.
        try:
            self.retry = sorted({int(i) for i in (g("retry") or [])})
        except (TypeError, ValueError):
            raise RootCanalError(
                "The events to search again have to be a list of event "
                "numbers.")
        cen = g("centres")
        if cen in (None, "", []):
            self.centres = None
        else:
            try:
                arr = np.asarray(cen, dtype=float)
            except (TypeError, ValueError):
                arr = np.zeros(0)
            if arr.shape != (self.k, 3) or not np.isfinite(arr).all():
                raise RootCanalError(
                    "The cluster centres have to be %d point%s of three "
                    "numbers each, in z units -- one per cluster -- or "
                    "nothing, for k-means' own."
                    % (self.k, "" if self.k == 1 else "s"))
            self.centres = [[float(v) for v in row] for row in arr]

        if self.filt != "none" and (self.order < 1 or self.order > 8):
            raise RootCanalError("The filter order has to be 1 to 8.")
        if self.filt == "none":
            pass
        elif self.lo_hz < 0:
            raise RootCanalError("The filter's low corner cannot be negative.")
        elif not self.lo_hz < self.hi_hz:
            raise RootCanalError(
                "The filter's high corner (%g Hz) has to be above its low "
                "corner (%g Hz)." % (self.hi_hz, self.lo_hz))
        elif self.hi_hz > MAX_HI_HZ:
            raise RootCanalError(
                "The waveforms are stored at %g Hz, so a lowpass above %g Hz "
                "would be shaped by the storage step's own anti-alias filter "
                "rather than by yours. Use %g Hz or less."
                % (self.snip_fs, MAX_HI_HZ, MAX_HI_HZ))
        if not 1.0 <= self.win_ms <= DISPLAY_MS:
            raise RootCanalError(
                "The amplitude window has to be between 1 and %g ms either "
                "side of the stamp." % DISPLAY_MS)
        lo_c, hi_c = CROSS_MS_RANGE
        if not lo_c <= self.cross_ms <= hi_c:
            raise RootCanalError(
                "The half-width search has to reach between %g and %g ms "
                "either side of the stamp (v1's is %g), not %g ms."
                % (lo_c, hi_c, V1_CROSS_MS, self.cross_ms))
        nyq = self.read_fs / 2.0
        if not 0 <= self.band_lo < self.band_hi:
            raise RootCanalError(
                "The HF band's high edge (%g Hz) has to be above its low edge "
                "(%g Hz)." % (self.band_hi, self.band_lo))
        top = nyq * DECIMATE_CORNER
        if self.band_hi > top:
            raise RootCanalError(
                "The HF band cannot go above %g Hz. The read is at %g Hz and "
                "its anti-alias filter starts cutting at %g Hz, so power "
                "above that is what the filter left, not what was there."
                % (top, self.read_fs, top))

    # -- the split --------------------------------------------------------
    def read_params(self):
        return {k: getattr(self, k) for k in self.READ_KEYS}

    def fit_params(self):
        return {k: getattr(self, k) for k in self.FIT_KEYS}

    def as_dict(self):
        out = dict(self.read_params())
        out.update(self.fit_params())
        out["from_version"] = self.from_version
        return out

    def read_hash(self):
        blob = self.read_params()
        keep = {k: blob.get(k) for k in self.READ_KEYS
                if blob.get(k) is not None}
        s = json.dumps(keep, sort_keys=True, default=str)
        return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]

    def band_label(self):
        return "%s–%s Hz power" % (_g(self.band_lo), _g(self.band_hi))

    def filter_label(self):
        """What the amplitude and half-width were measured on, in words."""
        if self.filt == "none":
            return "no filter (60 Hz mains left in)"
        name = FILTERS.get(self.filt, {}).get("label", "custom filter")
        lo = ("%s–%s Hz" % (_g(self.lo_hz), _g(self.hi_hz)) if self.lo_hz > 0
              else "low-pass %s Hz" % _g(self.hi_hz))
        return "%s, %s, %s" % (name, lo, "60 Hz mains out" if self.mains_out
                               else "60 Hz mains left in")


def _num(v, default, what):
    if v is None or v == "":
        return float(default)
    try:
        out = float(v)
    except (TypeError, ValueError):
        raise RootCanalError("%s has to be a number, not %r."
                             % (what[0].upper() + what[1:], v))
    if not np.isfinite(out):
        raise RootCanalError("%s has to be a finite number."
                             % (what[0].upper() + what[1:]))
    return out


def _g(v):
    return ("%.0f" % v) if float(v) == int(v) else ("%g" % v)


# --------------------------------------------------------------------------
# The expensive half
# --------------------------------------------------------------------------
def _ratio(fs_in, fs_out):
    """up/down for `resample_poly`, exact where the rates allow it.

    30 kHz / 6 = 5 kHz, and 5 kHz -> 2 kHz is 2/5. A 32 kHz file decimates to
    5333 Hz and 2000/5333 is 3/8 -- also exact. The denominator cap only
    matters for a rate nobody records at.
    """
    fr = Fraction(float(fs_out) / float(fs_in)).limit_denominator(64)
    return max(1, fr.numerator), max(1, fr.denominator)


def _cut(x, fs, t0, t, half_s):
    """The +-half_s window of `x` centred on `t`, or None if it is not whole.

    Whole or nothing, where `dspcahf` clips at the edges: every window here
    becomes a PSD on one frequency grid for the whole read, and a clipped
    window would put that one event's spectrum on a different grid.
    """
    c = int(round((t - t0) * fs))
    h = int(round(half_s * fs))
    lo, hi = c - h, c + h + 1
    if lo < 0 or hi > x.size:
        return None
    return x[lo:hi]


def read(session, channels, stamps, p, bad=None, job=None, stop=None,
         progress=None):
    """Every event's snippet and PSDs, on every contact. Minutes.

    `stamps` is [{"t": seconds, ...}], and the rows that come back are in
    THAT order: row i is stamp i, whatever order the spans were read in.

    `stop` is asked before every span, and `job.check()` as well when a job
    is given, so a Stop lands inside a channel rather than at the end of the
    recording. A batch passes `stop=job.check` and no `job`, because the
    batch owns the progress bar and a read that called `begin` would rescale
    it to channels (see `dspca.read`). `progress(done, of)`, if given, is
    told after each channel, which is how a batch fills in its member row
    without owning a stage.

    Returns a dict (see `save_read` for which parts reach the disk):
        t          [n] the stamp times
        nums       contact numbers, in the recording's channel order
        snip       [n x ch x T] float16 uV, median-removed, at `snip_fs`
        snip_off   [n x ch] float32, the medians that were removed
        f_ev, psd_ev      event-window Welch PSDs [n x ch x F]
        f_base, psd_base  baseline-window PSDs [n x ch x Fb]
        bad        {number: why}, the contacts left out of every pick
        missed     events no channel could be read for
    """
    if not HAVE_SCIPY:
        raise RootCanalError("This step needs scipy, which is not installed.")
    if not stamps:
        raise RootCanalError("That set has no events to measure.")
    reach_ms = max(p.snip_ms, p.hf_base_off_ms + p.hf_base_win_ms / 2.0,
                   p.hf_win_ms)
    if p.hf_base_off_ms + p.hf_base_win_ms / 2.0 > p.snip_ms:
        raise RootCanalError(
            "The HF baseline window reaches past the stored snippet.")

    nums = [int(c["number"]) for c in channels]
    n_ch = len(nums)
    ts = np.array([float(e["t"]) for e in stamps], dtype=float)
    n_ev = ts.size

    order = np.argsort(ts, kind="stable")
    runs = braces.spans([float(t) for t in ts], window_ms=reach_ms,
                        pad_s=p.pad_s, merge_gap=MERGE_GAP_S)
    # Which events each span serves, walked in time order the way
    # `dspca.read` does it.
    members, at = [], 0
    for a, b in runs:
        mine = []
        while at < n_ev and ts[order[at]] <= b - p.pad_s + 1e-9:
            mine.append(int(order[at]))
            at += 1
        members.append(mine)
    while at < n_ev:                     # cannot happen; kept honest anyway
        members[-1].append(int(order[at]))
        at += 1

    h2 = int(round(p.snip_ms / 1000.0 * p.snip_fs))
    n_t = 2 * h2 + 1
    snip = np.full((n_ev, n_ch, n_t), np.nan, dtype=np.float16)
    off = np.full((n_ev, n_ch), np.nan, dtype=np.float32)
    got_any = np.zeros(n_ev, dtype=bool)
    psd_ev = psd_base = f_ev = f_base = None
    fs5_seen = fs2_seen = None
    ev_half = p.hf_win_ms / 1000.0
    base_off = p.hf_base_off_ms / 1000.0
    base_half = p.hf_base_win_ms / 2000.0

    if job:
        job.begin(STAGE_READ, of=n_ch, unit="channels")
    for j, ch in enumerate(channels):
        if job:
            job.tick(STAGE_READ, j)
        if progress:
            progress(j, n_ch)
        for (a, b), mine in zip(runs, members):
            if stop:
                stop()
            if job:
                job.check()
            if not mine:
                continue
            raw, t0, ch_fs = csc._read_channel_window(session, ch, a, b)
            raw = np.asarray(raw)
            if raw.size < 64:
                continue
            q = incisor.decimation_for(ch_fs, p.read_fs)
            x5 = (incisor._decimate(raw, q) if q > 1
                  else np.asarray(raw, dtype=np.float64))
            fs5 = float(ch_fs) / q
            up, down = _ratio(fs5, p.snip_fs)
            x2 = resample_poly(x5, up, down)
            fs2 = fs5 * up / down
            fs5_seen, fs2_seen = fs5, fs2

            ev_rows, ev_segs, ba_segs = [], [], []
            for i in mine:
                t = ts[i]
                seg = _cut(x2, fs2, t0, t, h2 / fs2)
                if seg is None or seg.size != n_t:
                    continue
                med = float(np.median(seg))
                snip[i, j] = (seg - med).astype(np.float16)
                off[i, j] = med
                got_any[i] = True
                e = _cut(x5, fs5, t0, t, ev_half)
                bseg = _cut(x5, fs5, t0, t - base_off, base_half)
                if e is None or bseg is None:
                    continue
                ev_rows.append(i)
                ev_segs.append(e)
                ba_segs.append(bseg)
            if not ev_rows:
                continue
            # One Welch per span rather than per event: the windows are all
            # the same length, so they stack as columns.
            fe, Pe = dspcahf._psd(np.array(ev_segs).T, fs5)
            fb, Pb = dspcahf._psd(np.array(ba_segs).T, fs5)
            if psd_ev is None:
                f_ev, f_base = fe, fb
                psd_ev = np.full((n_ev, n_ch, fe.size), np.nan,
                                 dtype=np.float32)
                psd_base = np.full((n_ev, n_ch, fb.size), np.nan,
                                   dtype=np.float32)
            if fe.size != f_ev.size or fb.size != f_base.size:
                # A channel at a different rate from the rest. Not seen in
                # this lab; refused rather than mixed onto one grid.
                raise RootCanalError(
                    "CSC%d is not at the same sampling rate as the other "
                    "channels, so its spectra cannot be put beside theirs."
                    % nums[j])
            psd_ev[ev_rows, j] = Pe.T
            psd_base[ev_rows, j] = Pb.T

    missed = [int(i) for i in np.flatnonzero(~got_any)]
    if not got_any.any():
        raise RootCanalError(
            "None of those %d stamp(s) could be read -- every window was past "
            "the end of the recording, inside a gap, or too short to measure."
            % n_ev)
    if psd_ev is None:
        raise RootCanalError(
            "No event had a whole HF window and baseline inside the read, so "
            "no HF power could be measured.")

    try:
        runs_g, _probe = dspca.geometry(p.probe, channels)
    except dspca.DsPcaError:
        runs_g = [{"id": "line", "label": "the whole shank",
                   "rows": list(range(n_ch)), "numbers": nums}]
    spacing = p.spacing
    if spacing is None:
        spacing = dspca.spacing_for(p.probe)
    return {
        "t": ts,
        "nums": nums,
        "snip": snip,
        "snip_off": off,
        "snip_fs": float(fs2_seen or p.snip_fs),
        "snip_ms": float(p.snip_ms),
        "read_fs": float(fs5_seen or p.read_fs),
        "f_ev": np.asarray(f_ev, dtype=np.float64),
        "psd_ev": psd_ev,
        "f_base": np.asarray(f_base, dtype=np.float64),
        "psd_base": psd_base,
        "bad": {int(k): v for k, v in (bad or {}).items()},
        "missed": missed,
        "probe": p.probe,
        "spacing_um": float(spacing),
        "runs": [{"id": r["id"], "label": r["label"], "rows": r["rows"],
                  "numbers": r["numbers"]} for r in runs_g],
        "n_spans": len(runs),
    }


# --------------------------------------------------------------------------
# Filing a read
# --------------------------------------------------------------------------
_ARRAYS = ("t", "snip", "snip_off", "f_ev", "psd_ev", "f_base", "psd_base")
_META = ("nums", "snip_fs", "snip_ms", "read_fs", "bad", "missed", "probe",
         "spacing_um", "runs", "n_spans")


def save_read(path, got):
    """File one read. Written beside and moved, so a crash leaves no half.

    Plain arrays and a JSON string, no pickles, for the reason `dspca`
    gives: a cache only one numpy can read is not a shared cache.
    """
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    meta = {k: got.get(k) for k in _META}
    meta["bad"] = {str(k): v for k, v in (got.get("bad") or {}).items()}
    tmp = path + ".part.npz"
    np.savez_compressed(tmp, meta=np.array(json.dumps(meta, default=str)),
                        **{k: np.asarray(got[k]) for k in _ARRAYS})
    os.replace(tmp, path)
    return path


def load_read(path):
    """The dict `read` returned, back off the disk."""
    if not os.path.exists(path):
        raise RootCanalError(
            "That read is not on this machine any more. It is a cache, so "
            "nothing is lost -- read the set again.")
    with np.load(path, allow_pickle=False) as z:
        meta = json.loads(str(z["meta"]))
        got = dict(meta)
        for k in _ARRAYS:
            got[k] = np.asarray(z[k])
    got["bad"] = {int(k): v for k, v in (meta.get("bad") or {}).items()}
    got["missed"] = [int(i) for i in (meta.get("missed") or [])]
    return got


def subset(got, times):
    """The rows of a read for these stamp times, or None if any is missing.

    A set Root Canal has just cleaned is a SUBSET of the set it read: same
    recording, same stamps, fewer of them. Its stamps hash is different --
    it is a different list -- but every number it needs is already on disk,
    and re-reading minutes of recording to get back rows already held would
    be the cache failing at the one moment it is most obviously right.
    Matched at the stamps hash's own resolution, four decimals.
    """
    at = {round(float(t), 4): i for i, t in enumerate(got["t"])}
    idx = [at.get(round(float(t), 4)) for t in times]
    if not idx or any(i is None for i in idx):
        return None
    out = {k: v for k, v in got.items() if k != "_memo"}
    for k in ("t", "snip", "snip_off", "psd_ev", "psd_base"):
        out[k] = np.asarray(got[k])[idx]
    was = set(got.get("missed") or [])
    out["missed"] = [j for j, i in enumerate(idx) if i in was]
    return out


# --------------------------------------------------------------------------
# v1's measurement, ported (ied_ampwidth.py). The logic is unchanged; the
# rail check is not carried, because the rail is a fact about the raw
# 30 kHz samples and this works from a 2 kHz snippet.
# --------------------------------------------------------------------------
def _cross(y, pk, level, direction, lo, hi):
    """Walk out from `pk` to where `y` falls through `level`.

    Returns (index_float, edge_limited). `edge_limited` means the trace never
    came back below half-amplitude before the search ran out: there is no
    crossing, and the caller reports the width as unresolved rather than
    interpolating off the last pair of samples as though there were one.
    """
    i = int(pk)
    if direction < 0:
        while i > lo and y[i] >= level:
            i -= 1
        if y[i] >= level:
            return float(lo), True
        y0, y1 = y[i], y[i + 1]
        frac = (level - y0) / (y1 - y0) if y1 != y0 else 0.0
        return i + frac, False
    while i < hi and y[i] >= level:
        i += 1
    if y[i] >= level:
        return float(hi), True
    y0, y1 = y[i - 1], y[i]
    frac = (level - y0) / (y1 - y0) if y1 != y0 else 0.0
    return (i - 1) + frac, False


def _local_baseline(y, anchor, fs, flank_ms):
    """The median of the two flanking windows, outside the event (v1's
    `local`). What the trace was doing either side of it, rather than zero,
    which is wherever the amplifier happened to sit."""
    f0 = int(round(flank_ms[0] * 1e-3 * fs))
    f1 = int(round(flank_ms[1] * 1e-3 * fs))
    n = len(y)
    picks = []
    a0, a1 = anchor - f1, anchor - f0
    if a1 > 0:
        picks.append(y[max(0, a0):max(1, a1)])
    b0, b1 = anchor + f0, anchor + f1
    if b0 < n:
        picks.append(y[min(n - 1, b0):min(n, b1)])
    picks = [q for q in picks if q.size]
    if not picks:
        return float(np.median(y))
    return float(np.median(np.concatenate(picks)))


def measure_peak(y, anchor, fs, polarity, peak_ms, cross_ms,
                 flank_ms=FLANK_MS):
    """Amplitude and half-width of one polarity on one trace.

    v1's `measure_peak` with `baseline="local"`: the extremum inside
    +-`peak_ms` of `anchor`, the crossings hunted in the wider +-`cross_ms`,
    both in the oriented frame (peak positive) so the min polarity is the max
    one on a flipped trace and there is one code path.
    """
    n = len(y)
    sgn = 1.0 if polarity == "max" else -1.0
    s = sgn * np.asarray(y, dtype=float)
    pw = int(round(peak_ms * 1e-3 * fs))
    cw = int(round(cross_ms * 1e-3 * fs))
    plo, phi = max(0, anchor - pw), min(n - 1, anchor + pw)
    clo, chi = max(0, anchor - cw), min(n - 1, anchor + cw)
    if phi <= plo or not np.isfinite(s[plo:phi + 1]).all():
        return None
    pk = int(plo + np.argmax(s[plo:phi + 1]))
    base_s = _local_baseline(s, anchor, fs, flank_ms)
    amp = float(s[pk] - base_s)
    out = {"polarity": polarity, "peak_i": pk,
           "peak_ms": (pk - anchor) / fs * 1e3, "amp_uV": amp,
           "signed_peak_uV": float(sgn * s[pk]),
           "baseline_uV": float(sgn * base_s)}
    if not np.isfinite(amp) or amp <= 0:
        out.update({"status": "no_deflection", "half_level_uV": np.nan,
                    "left_ms": np.nan, "right_ms": np.nan, "hw_ms": np.nan,
                    "unresolved": False})
        return out
    level = base_s + 0.5 * amp
    li, l_edge = _cross(s, pk, level, -1, clo, chi)
    ri, r_edge = _cross(s, pk, level, +1, clo, chi)
    unresolved = bool(l_edge or r_edge)
    hw = (ri - li) / fs * 1e3 if ri > li else float("nan")
    out.update({
        "status": "ok",
        "half_level_uV": float(sgn * level),
        "left_ms": (li - anchor) / fs * 1e3,
        "right_ms": (ri - anchor) / fs * 1e3,
        # NaN, not the edge-limited number. See the module docstring.
        "hw_ms": float("nan") if unresolved else hw,
        "unresolved": unresolved,
    })
    return out


def _check_cross(got, p):
    """Refuse a half-width search the stored snippet cannot carry.

    The search has to stop well inside the snippet, not at its edge: the
    last tens of milliseconds of a +-250 ms snippet are where the zero-phase
    filter's padding lives, and a crossing found there would be a crossing
    of the padding. `CROSS_EDGE_MS` of margin is what makes 200 ms the
    ceiling on the stored 250.
    """
    room = float(got.get("snip_ms") or SNIP_MS) - CROSS_EDGE_MS
    if p.cross_ms > room:
        raise RootCanalError(
            "The stored waveforms reach +-%g ms, so the half-width search can "
            "go out to %g ms at most -- the last %g ms are the filter's "
            "margin. Use %g ms or less, or read the set again with a longer "
            "snippet." % (float(got.get("snip_ms") or SNIP_MS), room,
                          CROSS_EDGE_MS, room))


def retry_cross_ms(got):
    """The widest half-width search this read's snippets can carry: the
    setting's own ceiling, or less where the snippet is shorter (see
    `_check_cross`)."""
    room = float(got.get("snip_ms") or SNIP_MS) - CROSS_EDGE_MS
    return float(min(CROSS_MS_RANGE[1], room))


def _best_polarity(y, anchor, fs, p):
    """Both polarities, and the one that carries the event (v4)."""
    got = {pol: measure_peak(y, anchor, fs, pol, p.win_ms, p.cross_ms,
                             p.flank_ms) for pol in ("max", "min")}

    def size(m):
        return m["amp_uV"] if (m and m.get("status") == "ok") else -np.inf
    pol = "max" if size(got["max"]) >= size(got["min"]) else "min"
    return pol, got[pol]


# --------------------------------------------------------------------------
# The cheap half
# --------------------------------------------------------------------------
def _sos(p, fs):
    nyq = fs / 2.0
    hi = min(p.hi_hz, nyq * 0.99)
    if p.lo_hz > 0:
        return butter(p.order, [p.lo_hz / nyq, hi / nyq], btype="band",
                      output="sos")
    return butter(p.order, hi / nyq, btype="low", output="sos")


def _filter(x, p, fs):
    """Zero-phase, along time. NaN rows stay NaN rows and touch nothing.

    MIRRORED ACROSS THE WHOLE SNIPPET, not scipy's default. `sosfiltfilt`
    pads by an odd extension of 3*(2*sections+1) samples -- 27 at order 4,
    13 ms -- which is nothing against the ~160 ms a 1 Hz high-pass takes to
    settle. On a 500 ms snippet that default moved the pick to a different
    contact on 3 of 12 real events and one amplitude by 24%. An even
    extension a snippet long keeps the level at the edges where it was and
    gives the high-pass room to settle outside the part that is measured;
    measured against the continuous read it is the variant that agreed (see
    the module docstring for the numbers, and the two others that were
    tried and did worse).
    """
    y = np.array(x, dtype=np.float64)
    if p.filt == "none":
        return y
    n = y.shape[-1]
    if p.mains_out:
        # Fitted out row by row where the row is finite; a NaN row (a
        # contact the read could not take) stays NaN and touches nothing.
        rows = y.reshape(-1, n)
        ok = np.isfinite(rows).all(axis=1)
        if ok.any():
            rows[ok] = _line_out(rows[ok], fs)
        y = rows.reshape(y.shape)
    return sosfiltfilt(_sos(p, fs), y, axis=-1, padtype="even",
                       padlen=max(0, n - 1))


# THE CSD'S FILTER IS THE DENTATE-SPIKE ONE, not the fit filter.
#
# The fit filter (1-100 Hz by default) is what the amplitude and half-width
# are measured on. The CSD is a picture of WHERE a dentate spike's sink is,
# and the Dentist already has one filter for that: X-ray's, which is
# Braces' 60 Hz notch followed by Toothy's 5-100 Hz detection band
# (`braces._notch`, then `incisor._filtered`'s band and order).
#
# MEASURED, on the 18 recordings with a cached read here, a dozen events
# each, through this module's own event view: on the fit filter the share
# of CSD power at 55-65 Hz had a median of 5% across recordings and reached
# 72-78% on some (PTEN m1 s2, m1 s8). The voltage stack beside it carried
# 1-5% on most -- which is why the traces looked clean and the CSD did not.
# A CSD is a second difference across contacts, and mains that differs a
# little from one contact to the next survives it where it cancels by eye
# in the traces. That is the memory "mains is inside the DS band", seen
# from the other side.
CSD_BAND = tuple(incisor.DS_BAND)          # 5-100 Hz, Toothy's ds_freq
CSD_ORDER = incisor.DS_ORDER
CSD_LINE_HZ = braces.LINE_HZ               # 60 Hz
CSD_LINE_Q = braces.LINE_Q


def _line_out(y, fs, f0=CSD_LINE_HZ):
    """Take the mains out of each row by FITTING it, not by notching it.

    X-ray notches the continuous recording, where a 2 Hz-wide IIR notch has
    all the time it needs. A snippet does not: that notch takes ~160 ms to
    settle and the snippet is +-250 ms, so the part that is measured sits
    inside its transient. Measured on a pure 60 Hz sine through the notch
    on this snippet: less than 20 dB taken out. On the real reads it left
    9-13% of the 5-100 Hz power at 60 Hz on PTEN m1's noisiest contacts,
    which is what striped the CSD.

    Mains is one frequency for the whole snippet -- 30 cycles of it -- so its
    amplitude and phase are a two-number least-squares fit, and subtracting
    the fitted sine takes it out with no ringing at all. A 50 ms dentate
    spike projects on a 30-cycle sinusoid by almost nothing, so the event is
    left where it was.
    """
    if not (0 < f0 < 0.95 * (fs / 2.0)):
        return y
    n = y.shape[-1]
    t = np.arange(n) / float(fs)
    B = np.vstack([np.cos(2 * np.pi * f0 * t), np.sin(2 * np.pi * f0 * t),
                   np.ones(n)]).T                          # [n x 3]
    coef, *_ = np.linalg.lstsq(B, y.T, rcond=None)         # [3 x rows]
    return y - (B[:, :2] @ coef[:2]).T


def _ds_filter(x, fs):
    """The dentate-spike filter, on a snippet: mains out, then band-pass.

    The band-pass is padded the way `_filter` is -- an even extension a
    snippet long -- for the same reason. The mains is fitted out first; see
    `_line_out` for why it is not notched.
    """
    y = np.nan_to_num(np.asarray(x, dtype=np.float64))
    n = y.shape[-1]
    pad = max(0, n - 1)
    y = _line_out(y, fs)
    nyq = fs / 2.0
    sos = butter(CSD_ORDER, [CSD_BAND[0] / nyq, min(CSD_BAND[1], nyq * 0.99)
                             / nyq], btype="band", output="sos")
    return sosfiltfilt(sos, y, axis=-1, padtype="even", padlen=pad)


def _bad_rows(got, extra=()):
    want = {int(n) for n in (got.get("bad") or {})} | {int(n) for n in extra}
    return np.array([int(n) in want for n in got["nums"]], dtype=bool)


def _row_median(y):
    """`np.nanmedian(y, axis=-1)`, the same numbers, about three times
    faster.

    nanmedian walks every row in Python (`apply_along_axis`) once any NaN
    could be present, and that was most of a fit's time with no filter:
    1.7 s of 1.9 s on a 486-event read (measured 2026-10-06). A finite row's
    nanmedian IS its median, so every row is taken at once and only a row
    with a NaN in it goes the slow way.
    """
    base = np.median(y, axis=-1)
    gap = np.isnan(base)
    if gap.any():
        flat = y.reshape(-1, y.shape[-1])
        fb = base.reshape(-1)
        idx = np.flatnonzero(gap.reshape(-1))
        # An all-NaN row (a contact the read could not take) stays NaN,
        # without nanmedian's warning about it.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            fb[idx] = np.nanmedian(flat[idx], axis=-1)
        base = fb.reshape(base.shape)
    return base


# Filtering the stack is the expensive half of a fit: every contact of
# every event, zero-phase with a snippet-long extension. scipy's sosfilt
# lets go of the interpreter while it runs, so a few chunks at once go
# about twice as fast, with the same numbers to the bit. Bounded: at most
# FILTER_AHEAD chunks of FILTER_STEP events are held at once, so the
# float64 working copy stays tens of megabytes, as it was.
FILTER_STEP = 24
FILTER_WORKERS = min(4, os.cpu_count() or 1)
FILTER_AHEAD = FILTER_WORKERS + 1


def _filtered_chunks(snip, p, fs, bad, c, h):
    """(first event, filtered chunk, pick) for every FILTER_STEP events, in
    order, filtered a few at a time on threads."""
    n_ev = snip.shape[0]
    starts = iter(range(0, n_ev, FILTER_STEP))

    def work(s0):
        yf = _filter(snip[s0:s0 + FILTER_STEP], p, fs)
        return s0, yf, _pick(yf, bad, c, h)

    if FILTER_WORKERS <= 1:
        for s0 in starts:
            yield work(s0)
        return
    with ThreadPoolExecutor(FILTER_WORKERS,
                            thread_name_prefix="rc-filter") as ex:
        ahead = collections.deque()
        for s0 in starts:
            ahead.append(ex.submit(work, s0))
            if len(ahead) >= FILTER_AHEAD:
                break
        while ahead:
            done = ahead.popleft().result()
            nxt = next(starts, None)
            if nxt is not None:
                ahead.append(ex.submit(work, nxt))
            yield done


def _pick(yf, bad_rows, c, h):
    """v4's `winning_contact`: the largest |x - median| inside +-h samples.

    `yf` is [.., ch, T]. The median is over the whole snippet, per contact,
    which is v4's `st._base` over its whole cached view.
    """
    base = _row_median(yf)
    dev = np.abs(yf[..., c - h:c + h + 1] - base[..., None]).max(axis=-1)
    dev = np.where(np.isfinite(dev), dev, -np.inf)
    dev[..., bad_rows] = -np.inf
    return dev


def _measure(got, p):
    """Amplitude, half-width and contact for every event. Memoised.

    Keyed on the settings that change it (filter and window), so moving the
    band, a flip or a centre re-uses it and only a new filter pays for a
    re-filter of the stack -- which is done a few dozen events at a time, so
    the float64 working copy stays tens of megabytes rather than hundreds.
    """
    key = ("measure", p.filt, p.mains_out, p.lo_hz, p.hi_hz, p.order,
           p.win_ms, p.cross_ms, tuple(p.flank_ms))
    memo = got.setdefault("_memo", {})
    if key in memo:
        return memo[key]
    fs = float(got["snip_fs"])
    snip = got["snip"]
    n_ev, n_ch, n_t = snip.shape
    c = (n_t - 1) // 2
    h = int(round(p.win_ms * 1e-3 * fs))
    bad = _bad_rows(got)
    amp = np.full(n_ev, np.nan)
    hw = np.full(n_ev, np.nan)
    row = np.full(n_ev, -1, dtype=int)
    pol = [None] * n_ev
    detail = [None] * n_ev
    # A half-width found only because the search reaches past v1's 50 ms.
    # Decided by asking v1's search itself on the same trace and polarity --
    # not by looking at where the crossing landed -- so "wide" means exactly
    # "v1 would have called this unresolved".
    wide = np.zeros(n_ev, dtype=bool)
    for s0, yf, dev in _filtered_chunks(snip, p, fs, bad, c, h):
        for k in range(yf.shape[0]):
            i = s0 + k
            if not np.isfinite(dev[k]).any() or dev[k].max() == -np.inf:
                continue
            w = int(np.argmax(dev[k]))
            pl, m = _best_polarity(yf[k, w], c, fs, p)
            row[i] = w
            pol[i] = pl
            detail[i] = m
            if m is None or m.get("status") != "ok":
                continue
            amp[i] = m["amp_uV"]
            hw[i] = m["hw_ms"]
            if p.cross_ms > V1_CROSS_MS and np.isfinite(hw[i]):
                v1 = measure_peak(yf[k, w], c, fs, pl, p.win_ms, V1_CROSS_MS,
                                  p.flank_ms)
                wide[i] = bool(v1 and v1.get("unresolved"))
    out = {"amp": amp, "hw": hw, "row": row, "pol": pol, "detail": detail,
           "wide": wide}
    # A handful of filters are worth remembering and no more: each is a few
    # hundred numbers, but a session of somebody sweeping the corner would
    # otherwise grow without bound.
    # Four: the three presets `warm_measures` fills in, and one custom.
    old = [k for k in memo if k and k[0] == "measure"]
    for k in old[:-(MEASURES_KEPT - 1)]:
        memo.pop(k, None)
    memo[key] = out
    return out


# THE OTHER PRESETS, MEASURED BEFORE THEY ARE ASKED FOR. A filter is a
# click that refits at once, and a filter this read has not been measured
# on costs about two seconds of refiltering every contact (measured
# 2026-10-06 on a 486-event read; k, a relabel or the 3-axes switch cost
# under 0.1 s). So once a read has answered its first fit, the presets it
# has not been measured on are measured in the background, one at a time,
# at the same window and search -- and pressing DS or None finds them done.
MEASURES_KEPT = 4


def warm_measures(got, p):
    """Measure `got` on the preset filters it lacks, in a background thread.

    One warming per read at a time. Nothing is returned and nothing is
    written anywhere but the read's own memo, which is cache.
    """
    if got.get("_warming"):
        return None
    want = []
    for f in ("lfp", "ds", "none"):
        if f == p.filt:
            continue
        q = Params(**dict(p.fit_params(), filt=f))
        key = ("measure", q.filt, q.mains_out, q.lo_hz, q.hi_hz, q.order,
               q.win_ms, q.cross_ms, tuple(q.flank_ms))
        if key not in got.get("_memo", {}):
            want.append(q)
    if not want:
        return None
    got["_warming"] = True

    def run():
        try:
            for q in want:
                _measure(got, q)
        except Exception:                                # noqa: BLE001
            pass                    # a warm-up that fails is a cold click
        finally:
            got["_warming"] = False

    th = threading.Thread(target=run, daemon=True, name="rc-warm-measures")
    th.start()
    return th


def measure(got, p):
    """`_measure`, plus the events asked to be searched again wider.

    The retries are applied to a copy, never to the remembered answer: the
    same filter with no retries must still give the plain numbers.
    """
    base = _measure(got, p)
    if not p.retry:
        return dict(base, retried={})
    fs = float(got["snip_fs"])
    snip = got["snip"]
    n_ev = snip.shape[0]
    c = (snip.shape[2] - 1) // 2
    wide_ms = retry_cross_ms(got)
    out = {k: (v.copy() if isinstance(v, np.ndarray) else list(v))
           for k, v in base.items()}
    retried = {}
    for i in p.retry:
        if not 0 <= i < n_ev:
            continue
        w = int(out["row"][i])
        # Only a half-width that was NOT found: an event that has one keeps
        # it, and one with no deflection at all has nothing to search from.
        if w < 0 or np.isfinite(out["hw"][i]) or not np.isfinite(out["amp"][i]):
            continue
        yf = _filter(snip[i:i + 1], p, fs)[0]
        m2 = measure_peak(yf[w], c, fs, out["pol"][i], p.win_ms, wide_ms,
                          p.flank_ms)
        found = bool(m2 and m2.get("status") == "ok"
                     and np.isfinite(m2.get("hw_ms", np.nan)))
        retried[i] = found
        if found:
            out["hw"][i] = m2["hw_ms"]
            out["detail"][i] = m2
            # Found only past v1's search, so it is marked the way every
            # widened half-width is.
            out["wide"][i] = True
    out["retried"] = retried
    return out


def _band_power(f, P, lo, hi):
    m = (f >= lo) & (f < hi)
    if m.sum() < 2:
        return None
    trapz = getattr(np, "trapezoid", None) or np.trapz
    return trapz(P[..., m].astype(np.float64), f[m], axis=-1)


def hf_db(got, p):
    """[n x ch] dB of band power against the same contact's baseline, and the
    per-event best contact's value (v5's `best_db`), with its row."""
    pe = _band_power(got["f_ev"], got["psd_ev"], p.band_lo, p.band_hi)
    pb = _band_power(got["f_base"], got["psd_base"], p.band_lo, p.band_hi)
    if pe is None or pb is None:
        step = max(float(np.diff(got["f_ev"][:2])[0]),
                   float(np.diff(got["f_base"][:2])[0]))
        raise RootCanalError(
            "The band %s–%s Hz is too narrow for these spectra: a +-%g ms "
            "window has one frequency bin every %.0f Hz, and a band needs at "
            "least two. Widen it to %.0f Hz or more."
            % (_g(p.band_lo), _g(p.band_hi), got.get("hf_win_ms") or HF_WIN_MS,
               step, 2 * step))
    # A FLAT WINDOW HAS NO POWER, whatever the float says. v5's rule is NaN
    # where either side is not positive; a contact pinned to the amplifier's
    # rail for a whole window is a constant, whose band power is zero and
    # comes out of Welch as float noise -- measured, 5e-26 uV^2 on PTEN m13
    # s17 at 2958.924 s, where the baseline sat at +2000 uV, which made that
    # event +279 dB and the loudest thing in a pool of 2761. Anything nine
    # orders of magnitude below the read's typical window is that zero, and
    # is treated as one: no answer on that contact, rather than infinity.
    for P_ in (pe, pb):
        typical = np.nanmedian(np.where(P_ > 0, P_, np.nan))
        if np.isfinite(typical):
            P_[P_ < typical * 1e-9] = 0.0
    D = dspcahf._db(pe, pb)
    D[:, _bad_rows(got)] = np.nan
    ok = np.isfinite(D).any(axis=1)
    best = np.full(D.shape[0], np.nan)
    brow = np.full(D.shape[0], -1, dtype=int)
    if ok.any():
        best[ok] = np.nanmax(D[ok], axis=1)
        brow[ok] = np.nanargmax(np.where(np.isfinite(D[ok]), D[ok], -np.inf),
                                axis=1)
    return D, best, brow


def fit(got, p, margin=None):
    """The three numbers, the clustering, the naming, the overrides.

    Returns exactly what `/api/rootcanal/fit` sends, bar `ok`. Every event of
    the read is in `events`, in the read's order, measured or not -- an
    event left out of the list would be an event the panel cannot show as
    "not measured", and the count would silently not add up.
    """
    if not HAVE_SKLEARN:
        raise RootCanalError(dspca.NO_SKLEARN)
    t = np.asarray(got["t"], dtype=float)
    n = t.size
    nums = [int(v) for v in got["nums"]]
    _check_cross(got, p)
    m = measure(got, p)
    _D, hf, hf_row = hf_db(got, p)
    X = np.column_stack([m["amp"], m["hw"], hf])
    have = np.isfinite(X)
    n_axes = have.sum(axis=1)
    # Two groups, and only the first shapes the clusters. K-means, the
    # z-scoring and the centres are all computed from events measured on
    # all three axes; an event measured on exactly two is then ASSIGNED to
    # the nearer centre on the two it has. Nothing is made up for the third
    # -- no mean, no median, no nearest neighbour -- because an imputed
    # value would decide the class and look like a measurement. An event
    # with one axis or none has nothing to be near and stays unclassified.
    # The clustering itself is `cluster_core`, shared with Pooled: the
    # z-scoring, k-means for any k, the HF ranking, the naming rule,
    # dragged centres and saved margins. A margin, when there is one, has
    # already been checked against this fit's measurement by the caller.
    core = cluster_core(X, k=p.k, seed=p.seed, n_init=p.n_init,
                        centres=(None if margin else p.centres),
                        cluster_calls=p.cluster_calls, margin=margin,
                        margin_mode=(p.margin or {}).get("mode", "fixed"),
                        complete_only=p.complete_only,
                        drawn=[(g_["events"], g_["call"]) for g_ in p.drawn],
                        cluster_names=p.cluster_names)
    use, part, placed = core["use"], core["part"], core["placed"]
    n_used, mu, sd, Z = core["n_used"], core["mu"], core["sd"], core["Z"]
    C, raw_c, lab = core["C"], core["raw_c"], core["lab"]
    manual = core["manual"]
    # Every cluster's call, k-means' and the drawn ones after it.
    cls_of = {r: core["calls"][r]
              for r in range(core["k"] + core["n_drawn"])}

    flips = set(p.flips)
    events = []
    counts = {"ds": 0, "ied": 0, "unmeasured": 0, "partial": 0, "wide": 0,
              "excluded": 0}
    excl = core["excluded"]
    flipped_used = []
    why_part = {}
    for i in range(n):
        row = int(m["row"][i])
        missing = [AXES[k] for k in range(3) if not have[i, k]]
        wide_i = bool(m["wide"][i])
        if wide_i:
            counts["wide"] += 1
        if part[i]:
            counts["partial"] += 1
            why_part[missing[0]] = why_part.get(missing[0], 0) + 1
        if placed[i]:
            cl = int(lab[i])
            cls = cls_of[cl]
            fl = i in flips
            if fl:
                cls = "ied" if cls == "ds" else "ds"
                flipped_used.append(i)
            counts[cls] += 1
        else:
            cl, cls, fl = None, None, False
            # Left out by "complete events only" is not "not measured": it
            # was measured on two axes and set aside on purpose.
            counts["excluded" if excl[i] else "unmeasured"] += 1
        events.append({
            "excluded": bool(excl[i]),
            "i": i, "t": float(t[i]),
            "amp_uV": _f(m["amp"][i]), "hw_ms": _f(m["hw"][i]),
            "hf_db": _f(hf[i]),
            # A partial event's missing component is null, not a number:
            # it has no position on that axis and must not be drawn at one.
            "z": ([_f(v) for v in Z[i]] if placed[i] else None),
            "cluster": cl, "cls": cls, "flipped": fl,
            "axes": (int(n_axes[i]) if placed[i] else None),
            "partial": bool(part[i]),
            "missing": missing,
            "wide": wide_i,
            "contact": (nums[row] if row >= 0 else None),
            "contact_row": (row if row >= 0 else None),
            "polarity": m["pol"][i],
            # Where the HF number came from. Not always the max-amp contact:
            # v5's rule is the best contact for power, v4's the largest for
            # amplitude, and they need not agree.
            "hf_contact": (nums[int(hf_row[i])] if hf_row[i] >= 0 else None),
            "unresolved": bool((m["detail"][i] or {}).get("unresolved")),
            # Searched again wider on request: True found, False not.
            "retried": m["retried"].get(i),
            # Its cluster's name, when the cluster has one.
            "name": ((core.get("names") or [None])[cl]
                     if (cl is not None and cl < len(core.get("names") or []))
                     else None),
        })

    cls_of = {r: core["calls"][r]
              for r in range(core["k"] + core["n_drawn"])}
    centres = []
    for k in range(core["k"] + core["n_drawn"]):
        centres.append({"z": [_f(v) for v in C[k]],
                        "raw": [_f(v) for v in raw_c[k]],
                        "cls": cls_of[k],
                        # A drawn cluster's centre is the mean of what was
                        # drawn round; it is shown, never dragged.
                        "drawn": k >= core["k"],
                        "n": int((lab == k).sum())})
    general = k_sentence(core, p.band_label())
    # Widened by the setting, as against found by a retry: the retry has
    # its own sentence, with its own reach.
    n_wide_s = counts["wide"] - sum(1 for v in m["retried"].values() if v)
    ied_c = int(np.argmax(raw_c[:, 2])) if core["k"] >= 2 else 0
    ds_c = 1 - ied_c if core["k"] == 2 else 0
    rule = (
        "The cluster whose centre has more %s is called IED: %s dB against "
        "%s dB for the other, which is called DS (%d DS, %d IED%s%s%s%s%s)."
        % (p.band_label(), _db_s(raw_c[ied_c, 2]), _db_s(raw_c[ds_c, 2]),
           counts["ds"], counts["ied"],
           (", %d not measured" % counts["unmeasured"])
           if counts["unmeasured"] else "",
           ("; " + partial_sentence(counts["partial"], why_part, p.cross_ms))
           if counts["partial"] else "",
           ("; " + wide_sentence(n_wide_s, p.cross_ms))
           if n_wide_s else "",
           ("; centres placed by hand" if manual else ""),
           ("; %d flipped by hand" % len(flipped_used))
           if flipped_used else ""))
    if general:
        rule = ("%s (%d DS, %d IED%s%s%s%s%s)." % (
            general, counts["ds"], counts["ied"],
            (", %d not measured" % counts["unmeasured"])
            if counts["unmeasured"] else "",
            ("; " + partial_sentence(counts["partial"], why_part, p.cross_ms))
            if counts["partial"] else "",
            ("; " + wide_sentence(n_wide_s, p.cross_ms))
            if n_wide_s else "",
            ("; centres placed by hand" if manual else ""),
            ("; %d flipped by hand" % len(flipped_used))
            if flipped_used else ""))
    if core["n_drawn"]:
        nd = int(core["held"].sum())
        note = ("; %d event%s in %d cluster%s drawn by hand"
                % (nd, "" if nd == 1 else "s", core["n_drawn"],
                   "" if core["n_drawn"] == 1 else "s"))
        rule = (rule[:-2] + note + ")." if rule.endswith(").")
                else rule.rstrip(".") + note + ".")
    rt = m["retried"]
    if rt:
        nf = sum(1 for v in rt.values() if v)
        note = ("; %d of %d searched again to ±%s ms found a half-width"
                % (nf, len(rt), _g(retry_cross_ms(got))))
        rule = (rule[:-2] + note + ")." if rule.endswith(").")
                else rule.rstrip(".") + note + ".")
    unused = sorted(flips - set(flipped_used))
    return {
        "n": n, "n_used": n_used,
        # Placed in a cluster, which is the fitted ones and the partial ones.
        "n_placed": int(placed.sum()),
        "axes": [{"key": "amp_uV", "label": "max amplitude", "unit": "µV"},
                 {"key": "hw_ms", "label": "half-width", "unit": "ms"},
                 {"key": "hf_db", "label": p.band_label(),
                  "unit": "dB re baseline"}],
        "events": events,
        "centres": centres,
        "k": core["k"],
        "clusters": clusters_out(core),
        "k_from_margin": bool(margin) and core["k"] != p.k,
        "rule": rule,
        "counts": counts,
        "manual_centres": manual,
        # A flip on an event that is not measured has nothing to flip, so it
        # is reported rather than silently kept or silently dropped.
        "flips_ignored": unused,
        # The widest search a retry uses on this read, for the button.
        "retry_cross_ms": retry_cross_ms(got),
        "scale": {"mean": [float(v) for v in mu], "sd": [float(v) for v in sd]},
        "bad": {str(k): v for k, v in (got.get("bad") or {}).items()},
        "missed": list(got.get("missed") or []),
        "params": p.as_dict(),
    }


def margin_mismatch(margin, p):
    """How a saved margin's measurement differs from this fit's, in words.

    Empty when they agree. A margin is centres in µV, ms and dB; on a
    different filter, band or window those are different measurements, and
    a boundary drawn in one is not a boundary in the other.
    """
    m = (margin or {}).get("measure") or {}
    out = []
    mine = Params(**{k: getattr(p, k) for k in
                     ("filt", "mains_out", "lo_hz", "hi_hz", "order")})
    theirs_f = m.get("filter_label")
    if theirs_f and theirs_f != mine.filter_label():
        out.append("the margin was measured on %s and this on %s"
                   % (theirs_f, mine.filter_label()))
    for key, words in (("band_lo", None), ("win_ms", "amplitude window"),
                       ("cross_ms", "half-width search")):
        if key == "band_lo":
            a = [m.get("band_lo"), m.get("band_hi")]
            b = [p.band_lo, p.band_hi]
            if a[0] is not None and [float(a[0]), float(a[1])] != b:
                out.append("the margin's HF band was %s–%s Hz and this is "
                           "%s–%s Hz" % (_g(a[0]), _g(a[1]), _g(b[0]),
                                         _g(b[1])))
            continue
        a, b = m.get(key), getattr(p, key)
        if a is not None and float(a) != float(b):
            out.append("its %s was ±%s ms and this is ±%s ms"
                       % (words, _g(a), _g(b)))
    return out


def measure_of(p):
    """What a margin records about how its numbers were measured."""
    return {"filt": p.filt, "mains_out": bool(p.mains_out),
            "lo_hz": float(p.lo_hz), "hi_hz": float(p.hi_hz),
            "order": int(p.order), "filter_label": p.filter_label(),
            "win_ms": float(p.win_ms), "cross_ms": float(p.cross_ms),
            "band_lo": float(p.band_lo), "band_hi": float(p.band_hi)}


def cluster_core(X, k=K_DEFAULT, seed=SEED, n_init=N_INIT, centres=None,
                 cluster_calls=None, margin=None, margin_mode="fixed",
                 what="events", complete_only=False, drawn=None,
                 cluster_names=None):
    """One clustering, for Single and for Pooled alike.

    `X` is [n x 3] raw amp, hw, hf, NaN where unmeasured. Returns the scale,
    the z values, the centres ranked, every event's cluster and the call of
    every cluster. Kept in one place so the two views cannot drift apart.

    RANKS. k-means numbers its clusters arbitrarily, so they are put in
    order of their centre's raw HF power, lowest first: rank 0 is the
    quietest cluster, rank k-1 the loudest. At k = 2 that is the old
    "DS first". Dragged centres keep the order they were sent in (so a
    handle does not swap under the mouse), and so do a margin's.

    CALLS. At k >= 2 the highest-HF cluster is IED and the rest are DS -- the
    rule, generalised. At k = 1 everything is DS: with one cluster there is
    nothing to call an IED against. A margin brings its own calls. Calls
    given by hand (`cluster_calls`, by rank) win over both.

    MARGINS. A margin is read on ITS OWN scale (decided by the user): the
    centres were placed on the source's z, so the target is z-scored with
    the source's mean and SD, and the boundary is the same µV, ms and dB
    wherever it is used. Fixed: nearest margin centre, nothing moves.
    Refine: k-means on this data in that scale, started at the margin's
    centres, n_init = 1 -- each cluster keeps the call of the centre it
    started from.

    Partial events (two axes) are assigned on the axes they have and shape
    nothing; events with fewer are left out. See `fit`.
    """
    X = np.asarray(X, dtype=float).reshape(-1, 3)
    n = X.shape[0]
    have = np.isfinite(X)
    n_axes = have.sum(axis=1)
    use, part = n_axes == 3, n_axes == 2
    # Complete events only: an event on two axes is left out rather than
    # placed on them, and counted as left out.
    excluded = part.copy() if complete_only else np.zeros(n, dtype=bool)
    if complete_only:
        part = np.zeros(n, dtype=bool)
    # DRAWN BY HAND: those events are held out of k-means -- they shape no
    # centre and no scale -- and become clusters of their own afterwards.
    drawn = [(np.asarray(ix, dtype=int), str(call))
             for ix, call in (drawn or []) if len(ix)]
    held = np.zeros(n, dtype=bool)
    for ix, _call in drawn:
        held[ix[(ix >= 0) & (ix < n)]] = True
    use = use & ~held
    part = part & ~held
    placed = use | part
    n_used = int(use.sum())

    if margin:
        k = int(margin["k"])
        mu = np.asarray(margin["scale"]["mean"], dtype=float)
        sd = np.asarray(margin["scale"]["sd"], dtype=float)
    else:
        need = max(3, k)
        if n_used < need:
            raise RootCanalError(
                "Only %d of %d %s were measured on all three axes, and %d "
                "cluster%s need more than that." % (
                    n_used, n, what, k, "" if k == 1 else "s"))
        mu = X[use].mean(axis=0)
        sd = X[use].std(axis=0)
    sd = np.where(~np.isfinite(sd) | (sd == 0), 1.0, sd)
    Z = np.where(have, (X - mu) / sd, np.nan)

    keep_order = False
    if margin:
        Cm = (np.asarray([c["centre_raw"] for c in margin["clusters"]],
                         dtype=float) - mu) / sd
        if margin_mode == "refine":
            if n_used < k:
                raise RootCanalError(
                    "Refining a %d-cluster margin needs at least %d events "
                    "measured on all three axes; there are %d."
                    % (k, k, n_used))
            km = KMeans(n_clusters=k, init=Cm, n_init=1).fit(Z[use])
            C = np.asarray(km.cluster_centers_, dtype=float)
        else:
            C = Cm
        keep_order = True
    elif centres is not None:
        C = np.asarray(centres, dtype=float)
        keep_order = True
    elif k == 1:
        C = Z[use].mean(axis=0, keepdims=True)
    else:
        km = KMeans(n_clusters=k, random_state=seed, n_init=n_init)
        km.fit(Z[use])
        C = np.asarray(km.cluster_centers_, dtype=float)
    raw_c = C * sd + mu
    if not keep_order:
        o = np.argsort(raw_c[:, 2], kind="stable")
        C, raw_c = C[o].copy(), raw_c[o].copy()

    # Every event to its nearest centre, over the axes it has.
    lab = np.full(n, -1, dtype=int)
    if placed.any():
        diff = np.where(have[placed][:, None, :],
                        Z[placed][:, None, :] - C[None, :, :], 0.0)
        lab[placed] = np.argmin((diff ** 2).sum(axis=2), axis=1)

    if margin:
        calls = [str(c["call"]) for c in margin["clusters"]]
        by = ["margin"] * k
    else:
        calls, by = ["ds"] * k, ["rule"] * k
        if k >= 2:
            hfc = raw_c[:, 2]
            top = (int(np.argmax(hfc)) if np.unique(hfc).size > 1 else k - 1)
            calls[top] = "ied"
    for key, v in (cluster_calls or {}).items():
        r = int(key)
        if 0 <= r < k and v in ("ds", "ied") and v != calls[r]:
            calls[r], by[r] = v, "hand"
    # The drawn clusters, ranked after k-means' own, each centred on the
    # mean of its complete events (its two-axis ones where that is all it
    # has), with the call it was drawn with.
    if drawn:
        Cd, Rd = [], []
        for j, (ix, call) in enumerate(drawn):
            ix = ix[(ix >= 0) & (ix < n)]
            lab[ix] = k + j
            pick = ix[np.isfinite(X[ix]).all(axis=1)]
            src = pick if len(pick) else ix
            with np.errstate(invalid="ignore"):
                zc = np.nanmean(Z[src], axis=0) if len(src) else np.full(3, np.nan)
                rc_ = np.nanmean(X[src], axis=0) if len(src) else np.full(3, np.nan)
            Cd.append(zc)
            Rd.append(rc_)
            calls.append(call)
            by.append("drawn")
        C = np.vstack([C, np.asarray(Cd, dtype=float)])
        raw_c = np.vstack([raw_c, np.asarray(Rd, dtype=float)])
        placed = placed | held
    # NAMES, last: a named cluster's call is its name's type. A drawn one
    # keeps saying it was drawn; any other is called by its name.
    names = [None] * len(calls)
    for key, v in (cluster_names or {}).items():
        r = int(key)
        if 0 <= r < len(calls) and (v or {}).get("name"):
            names[r] = v["name"]
            if v.get("type") in ("ds", "ied"):
                calls[r] = v["type"]
                if by[r] != "drawn":
                    by[r] = "name"
    return {"n": n, "have": have, "n_axes": n_axes, "use": use,
            "names": names,
            "n_drawn": len(drawn), "held": held,
            "part": part, "placed": placed, "n_used": n_used,
            "excluded": excluded,
            "mu": mu, "sd": sd, "Z": Z, "C": C, "raw_c": raw_c, "lab": lab,
            "k": k, "calls": calls, "call_by": by,
            "manual": centres is not None and not margin}


def clusters_out(core):
    """The `clusters` list a fit hands back: one row per rank."""
    lab, C, raw_c = core["lab"], core["C"], core["raw_c"]
    nm = core.get("names") or []
    return [{"rank": r, "call": core["calls"][r], "call_by": core["call_by"][r],
             "name": nm[r] if r < len(nm) else None,
             "n": int((lab == r).sum()),
             "drawn": core["call_by"][r] == "drawn",
             "centre_raw": [_f(v) for v in raw_c[r]],
             "centre_z": [_f(v) for v in C[r]]}
            for r in range(core["k"] + core.get("n_drawn", 0))]


# ==========================================================================
# A SINGLE, KEPT: a fit as a version's payload, and back again
# ==========================================================================
# The numbers travel; the read does not. A saved Single is every event's
# three numbers and its call, column by column, rounded to what the
# measurement can mean (4 decimals of a microvolt, a millisecond or a dB;
# 6 of a second), which gzips to about 17 bytes an event -- a few KB for a
# set, so a version costs the shared database next to nothing (memory: big
# payloads took it down). Everything else the panel draws is rebuilt from
# them: the z values from the scale kept beside them, the centres and the
# clusters as they were.
SINGLE_SCHEMA = "rootcanal.single/1"
SINGLE_DP = 4
_POL = {"max": 1, "min": -1}
_POL_BACK = {1: "max", -1: "min"}


def _rd(v, dp=SINGLE_DP):
    v = _f(v)
    return None if v is None else round(float(v), dp)


def single_payload(res, meta=None):
    """One fit as a Single version's payload.

    `res` is what `fit` returns (with `params` as the route sends them);
    `meta` is who and where: entry_id, gid, session_label, project, mouse,
    mouse_key, read, read_on, from_version, from (what made this version:
    Single, or a pool or a double pool it was propagated from).
    """
    ev = res["events"]

    def col(fn):
        return [fn(e) for e in ev]
    cols = {
        "i": col(lambda e: int(e["i"])),
        "t": col(lambda e: round(float(e["t"]), 6)),
        "amp": col(lambda e: _rd(e["amp_uV"])),
        "hw": col(lambda e: _rd(e["hw_ms"])),
        "hf": col(lambda e: _rd(e["hf_db"])),
        "cluster": col(lambda e: e["cluster"]),
        "cls": col(lambda e: e["cls"]),
        "axes": col(lambda e: e["axes"]),
        "flags": col(lambda e: (1 if e.get("partial") else 0)
                     | (2 if e.get("wide") else 0)
                     | (4 if e.get("excluded") else 0)
                     | (8 if e.get("flipped") else 0)
                     | (16 if e.get("unresolved") else 0)),
        "retried": col(lambda e: (None if e.get("retried") is None
                                  else int(bool(e["retried"])))),
        "row": col(lambda e: e.get("contact_row")),
        "contact": col(lambda e: e.get("contact")),
        "hf_contact": col(lambda e: e.get("hf_contact")),
        "pol": col(lambda e: _POL.get(e.get("polarity"))),
    }
    fitp = {k: res["params"].get(k) for k in Params.FIT_KEYS
            if k in (res.get("params") or {})}
    out = {
        "schema": SINGLE_SCHEMA,
        "n": len(ev), "k": res["k"],
        "params": dict(res.get("params") or {}),
        "measure": measure_of(Params(**fitp)),
        "clusters": res.get("clusters") or [],
        "centres": res.get("centres") or [],
        "scale": res.get("scale") or {},
        "axes": res.get("axes") or [],
        "rule": res.get("rule"),
        "counts": res.get("counts") or {},
        "retry_cross_ms": res.get("retry_cross_ms"),
        "bad": res.get("bad") or {},
        "missed": res.get("missed") or [],
        "cols": cols,
    }
    out.update(meta or {})
    out["rows_digest"] = _single_digest(out)
    return out


def single_rows(payload):
    """A saved Single's events as pool rows -- what `rootcanalpool.fit_pool`
    takes from a member -- with no read. Each carries its cluster's name."""
    c = payload.get("cols") or {}
    names = {cl.get("rank"): cl.get("name")
             for cl in payload.get("clusters") or []}
    out = []
    for j in range(len(c.get("i") or [])):
        fl = int((c.get("flags") or [0])[j] or 0) if c.get("flags") else 0
        out.append({"i": int(c["i"][j]), "t": float(c["t"][j]),
                    "amp_uV": c["amp"][j], "hw_ms": c["hw"][j],
                    "hf_db": c["hf"][j], "cls": c["cls"][j],
                    "flipped": bool(fl & 8), "wide": bool(fl & 2),
                    "row": c["row"][j],
                    "pol": _POL_BACK.get(c["pol"][j]),
                    "name": names.get(c["cluster"][j])})
    return out


def _single_digest(payload):
    """The rows a saved Single holds, as a name -- what a pool pins it by."""
    rows = single_rows(payload)
    blob = json.dumps([[r["i"], r["t"], r["amp_uV"], r["hw_ms"], r["hf_db"],
                        r["cls"]] for r in rows], separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def single_fit_view(payload):
    """A saved Single as the Single panel's `fit`: the events with their z
    values (from the scale kept with them), centres, clusters, rule and
    counts. What opens a version where its read is not."""
    c = payload.get("cols") or {}
    sc = payload.get("scale") or {}
    names = {cl.get("rank"): cl.get("name")
             for cl in payload.get("clusters") or []}
    mu = [float(v) for v in (sc.get("mean") or [0, 0, 0])]
    sd = [float(v) or 1.0 for v in (sc.get("sd") or [1, 1, 1])]
    events = []
    for j in range(len(c.get("i") or [])):
        x = [c["amp"][j], c["hw"][j], c["hf"][j]]
        fl = int(c["flags"][j] or 0)
        placed = c["cluster"][j] is not None
        events.append({
            "i": int(c["i"][j]), "t": float(c["t"][j]),
            "amp_uV": x[0], "hw_ms": x[1], "hf_db": x[2],
            "z": ([None if v is None else (float(v) - mu[a]) / sd[a]
                   for a, v in enumerate(x)] if placed else None),
            "cluster": c["cluster"][j], "cls": c["cls"][j],
            "flipped": bool(fl & 8), "axes": c["axes"][j],
            "partial": bool(fl & 1), "wide": bool(fl & 2),
            "excluded": bool(fl & 4), "unresolved": bool(fl & 16),
            "missing": [AXES[a] for a in range(3) if x[a] is None],
            "contact": c["contact"][j], "contact_row": c["row"][j],
            "polarity": _POL_BACK.get(c["pol"][j]),
            "hf_contact": c["hf_contact"][j],
            "retried": (None if c["retried"][j] is None
                        else bool(c["retried"][j])),
            "name": names.get(c["cluster"][j]),
        })
    n_placed = sum(1 for e in events if e["cluster"] is not None)
    return {
        "n": payload.get("n", len(events)),
        "n_used": sum(1 for e in events if e["cluster"] is not None
                      and not e["partial"]),
        "n_placed": n_placed,
        "axes": payload.get("axes") or [],
        "events": events,
        "centres": payload.get("centres") or [],
        "k": payload.get("k"),
        "clusters": payload.get("clusters") or [],
        "rule": payload.get("rule"),
        "counts": payload.get("counts") or {},
        "scale": sc,
        "bad": payload.get("bad") or {},
        "missed": payload.get("missed") or [],
        "params": payload.get("params") or {},
        "retry_cross_ms": payload.get("retry_cross_ms"),
        "flips_ignored": [],
        "manual_centres": False,
        "k_from_margin": False,
        # The cluster tests' answer, when the version was saved with one.
        "stats": payload.get("stats"),
    }


def fit_rows(payload, p, margin=None):
    """`fit`, on a saved Single's numbers instead of its read.

    For what does not measure: a margin applied, k, names, relabels -- so a
    version can be re-clustered (a pool's identity propagated to it, say)
    on a machine its read never reached. The three numbers are the saved
    ones; `p` must measure the way they were measured, which the caller
    checks. Returns what `fit` returns, as far as stored numbers allow.
    """
    c = payload.get("cols") or {}
    n = len(c.get("i") or [])
    X = np.array([[np.nan if c["amp"][j] is None else c["amp"][j],
                   np.nan if c["hw"][j] is None else c["hw"][j],
                   np.nan if c["hf"][j] is None else c["hf"][j]]
                  for j in range(n)], dtype=float).reshape(-1, 3)
    core = cluster_core(X, k=p.k, seed=p.seed, n_init=p.n_init,
                        centres=(None if margin else p.centres),
                        cluster_calls=p.cluster_calls, margin=margin,
                        margin_mode=(p.margin or {}).get("mode", "fixed"),
                        complete_only=p.complete_only,
                        drawn=[(g_["events"], g_["call"]) for g_ in p.drawn],
                        cluster_names=p.cluster_names)
    placed, part, lab, Z = core["placed"], core["part"], core["lab"], core["Z"]
    names = core.get("names") or []
    counts = {"ds": 0, "ied": 0, "unmeasured": 0, "partial": 0, "wide": 0,
              "excluded": 0}
    events = []
    for j in range(n):
        fl = int((c.get("flags") or [0] * n)[j] or 0)
        cl = int(lab[j]) if placed[j] else None
        cls = core["calls"][cl] if cl is not None else None
        if cls:
            counts[cls] += 1
        else:
            counts["excluded" if core["excluded"][j] else "unmeasured"] += 1
        if part[j]:
            counts["partial"] += 1
        if fl & 2:
            counts["wide"] += 1
        events.append({
            "i": int(c["i"][j]), "t": float(c["t"][j]),
            "amp_uV": c["amp"][j], "hw_ms": c["hw"][j], "hf_db": c["hf"][j],
            "z": ([_f(v) for v in Z[j]] if placed[j] else None),
            "cluster": cl, "cls": cls, "flipped": False,
            "axes": int(np.isfinite(X[j]).sum()) if placed[j] else None,
            "partial": bool(part[j]), "wide": bool(fl & 2),
            "excluded": bool(core["excluded"][j]),
            "unresolved": bool(fl & 16),
            "retried": (None if c["retried"][j] is None
                        else bool(c["retried"][j])),
            "contact_row": c["row"][j], "contact": c["contact"][j],
            "hf_contact": c["hf_contact"][j],
            "polarity": _POL_BACK.get(c["pol"][j]),
            "name": names[cl] if cl is not None and cl < len(names) else None,
        })
    general = k_sentence(core, p.band_label()) or (
        "Clustered from the saved numbers")
    rule = "%s (%d DS, %d IED)." % (general.rstrip("."), counts["ds"],
                                    counts["ied"])
    return {
        "n": n, "n_used": int(core["n_used"]), "n_placed": int(placed.sum()),
        "axes": payload.get("axes") or [],
        "events": events,
        "centres": [{"z": [_f(v) for v in core["C"][r]],
                     "raw": [_f(v) for v in core["raw_c"][r]],
                     "cls": core["calls"][r], "drawn": r >= core["k"],
                     "n": int((lab == r).sum())}
                    for r in range(core["k"] + core["n_drawn"])],
        "k": core["k"],
        "clusters": clusters_out(core),
        "rule": rule, "counts": counts,
        "scale": {"mean": [float(v) for v in core["mu"]],
                  "sd": [float(v) for v in core["sd"]]},
        "bad": payload.get("bad") or {}, "missed": payload.get("missed") or [],
        "retry_cross_ms": payload.get("retry_cross_ms"),
        "params": dict(payload.get("params") or {}, **p.fit_params()),
    }


def k_sentence(core, band_label):
    """The naming rule, for any k, in one sentence -- or None at k = 2 by
    the rule alone, where the original sentence is kept word for word."""
    k, calls, by, raw_c = core["k"], core["calls"], core["call_by"], core["raw_c"]
    if k == 2 and by == ["rule", "rule"]:
        return None
    if k == 1:
        return ("k = 1: one cluster, so no split -- every event is called "
                "DS%s" % (" (relabelled IED by hand)"
                          if calls[0] == "ied" else ""))
    ied = [r for r in range(k) if calls[r] == "ied"]
    ds = [r for r in range(k) if calls[r] == "ds"]
    db = lambda rs: ", ".join(_db_s(raw_c[r, 2]) + " dB" for r in rs)
    head = ("k = %d%s: " % (k, ", from a saved margin"
                            if "margin" in by else ""))
    body = []
    if ied:
        body.append("the cluster%s at %s %s called IED"
                    % ("" if len(ied) == 1 else "s", db(ied),
                       "is" if len(ied) == 1 else "are"))
    if ds:
        body.append("the cluster%s at %s %s DS"
                    % ("" if len(ds) == 1 else "s", db(ds),
                       "is" if len(ds) == 1 else "are"))
    hand = [r for r in range(k) if by[r] == "hand"]
    tail = ""
    if hand:
        tail = " (cluster%s %s relabelled by hand)" % (
            "" if len(hand) == 1 else "s",
            ", ".join(str(r + 1) for r in hand))
    elif "margin" not in by:
        tail = " (the highest-HF cluster is IED by the rule)"
    return head + "; ".join(body) + tail + " on " + band_label


_WHY = {"hw_ms": "half-width unresolved even at %s ms",
        "hf_db": "no HF power measured",
        "amp_uV": "no amplitude measured"}


def partial_sentence(n, why, cross_ms):
    """ "2 assigned on 2 of 3 axes (half-width unresolved even at 50 ms)" """
    parts = []
    for key in AXES:
        if why.get(key):
            at = cross_ms if isinstance(cross_ms, str) else _g(cross_ms)
            txt = _WHY[key] % at if "%s" in _WHY[key] else _WHY[key]
            parts.append(txt if len(why) == 1 else "%d %s" % (why[key], txt))
    return "%d assigned on 2 of 3 axes (%s)" % (n, "; ".join(parts))


def wide_sentence(n, cross_ms):
    """ "1 resolved only with the half-width search widened to 80 ms" """
    return ("%d resolved only with the half-width search widened to %s ms"
            % (n, _g(cross_ms)))


def flag_times(res):
    """The times of the flagged events, for the bank. The per-event
    whitelist has no field for a flag, so the flags travel as lists of
    times beside the setting that produced them."""
    ev = res["events"]
    return {"partial_t": [e["t"] for e in ev if e.get("partial")],
            "wide_t": [e["t"] for e in ev if e.get("wide")],
            "cross_ms": float(res["params"].get("cross_ms") or CROSS_MS)}


def _f(v):
    return float(v) if v is not None and np.isfinite(v) else None


def _db_s(v):
    return ("%+.1f" % v) if np.isfinite(v) else "no"


# --------------------------------------------------------------------------
# One event, for the click panel
# --------------------------------------------------------------------------
def _display_idx(n_t, fs):
    """Samples within +-DISPLAY_MS of the centre, thinned to <= MAX_POINTS."""
    c = (n_t - 1) // 2
    h = int(round(DISPLAY_MS * 1e-3 * fs))
    lo, hi = max(0, c - h), min(n_t, c + h + 1)
    idx = np.arange(lo, hi)
    step = int(np.ceil(idx.size / float(MAX_POINTS)))
    return idx[::max(1, step)], c


def group_parts(got, p, idxs, rowpol=None):
    """Sums over a set of events of one read, for an average.

    WHAT IS AVERAGED, and how:
      trace     each event's own max-amp contact, the contact its amplitude
                was read off, with that event's local baseline taken off and
                aligned on the stamp. An event whose peak goes the other way
                from most is FLIPPED to the common polarity rather than left
                to cancel the rest -- and how many were is counted and said.
      spectrum  each event's spectrum on the contact its HF number came
                from, against its own baseline: linear power, averaged.
      stack     every contact, averaged as it is.
      CSD       of the average dentate-band trace (the CSD is linear, so
                this is the average CSD), down the column most of the
                events' max contacts are in.

    FILTERED ONCE, NOT PER EVENT, where that is the same answer. Both
    filters are linear -- the band-passes, and the mains fit, which is a
    least-squares projection -- so the average of filtered snippets IS the
    filtered average snippet. Filtering every contact of every event cost
    ~90 ms an event and a pooled average of 992 events took 55 s. The
    trace is the one thing that needs each event on its own (its own
    contact, baseline and polarity), and that is one contact: ~3 ms.
    """
    snip = got["snip"]
    n_ev, n_ch, n_t = snip.shape
    want = sorted({int(i) for i in idxs if 0 <= int(i) < n_ev})
    if not want:
        raise RootCanalError("There are no events of this read to average.")
    _check_cross(got, p)
    fs = float(got["snip_fs"])
    # Each event's max contact and polarity: handed in where the caller
    # already has them (a pool keeps them), measured here otherwise.
    if rowpol is not None and all(i in rowpol and rowpol[i][0] is not None
                                  for i in want):
        m = {"row": {i: int(rowpol[i][0]) for i in want},
             "pol": {i: rowpol[i][1] for i in want}}
    else:
        m = measure(got, p)
    _D, _best, brow = hf_db(got, p)
    c = (n_t - 1) // 2
    pols = [m["pol"][i] for i in want if m["row"][i] >= 0]
    ref = "max" if pols.count("max") >= pols.count("min") else "min"
    tr_sum = np.zeros(n_t)
    tr_sq = np.zeros(n_t)
    n_tr = flipped = 0
    raw_sum = np.zeros((n_ch, n_t))
    raw_n = np.zeros(n_ch)
    pe_sum = pb_sum = None
    n_sp = 0
    rows_hit = {}
    fe, fb = np.asarray(got["f_ev"]), np.asarray(got["f_base"])
    for i in want:
        x = np.asarray(snip[i], dtype=np.float64)
        ok = np.isfinite(x).all(axis=1)
        if not ok.any():
            continue
        raw_sum[ok] += x[ok]
        raw_n[ok] += 1
        w = int(m["row"][i])
        if w >= 0 and ok[w]:
            yw = _filter(x[w:w + 1], p, fs)[0]
            base = _local_baseline(yw, c, fs, p.flank_ms)
            sign = 1.0 if m["pol"][i] == ref else -1.0
            flipped += sign < 0
            y = sign * (yw - (base if np.isfinite(base) else 0.0))
            tr_sum += y
            tr_sq += y * y
            n_tr += 1
            rows_hit[w] = rows_hit.get(w, 0) + 1
        r = int(brow[i]) if brow[i] >= 0 else w
        if r >= 0:
            pe = np.asarray(got["psd_ev"][i, r], dtype=np.float64)
            pb = np.interp(fe, fb, np.asarray(got["psd_base"][i, r],
                                              dtype=np.float64))
            if np.isfinite(pe).all() and np.isfinite(pb).all():
                pe_sum = pe if pe_sum is None else pe_sum + pe
                pb_sum = pb if pb_sum is None else pb_sum + pb
                n_sp += 1
    return {"n": len(want), "n_trace": n_tr, "flipped": int(flipped),
            "ref": ref, "tr_sum": tr_sum, "tr_sq": tr_sq,
            "raw_sum": raw_sum, "raw_n": raw_n,
            "pe_sum": pe_sum, "pb_sum": pb_sum, "n_sp": n_sp, "f": fe,
            "rows_hit": rows_hit, "fs": fs, "n_t": n_t, "got": got}


def group_view(parts, p, label=None):
    """The four panels of the click panel, for an average.

    `parts` is one or more `group_parts`, from one read or several. The
    trace and the spectrum pool every event; the stack and the CSD are a
    probe-wide picture, which only means something inside one recording,
    so they come from the read that gave the most events and say which.
    """
    parts = [q for q in parts if q and q["n"]]
    if not parts:
        raise RootCanalError("There is nothing to average.")
    main = max(parts, key=lambda q: q["n"])
    got, fs, n_t = main["got"], main["fs"], main["n_t"]
    nums = [int(v) for v in got["nums"]]
    c = (n_t - 1) // 2
    idx, _c = _display_idx(n_t, fs)
    t_ms = (idx - c) / fs * 1e3

    n_tr = sum(q["n_trace"] for q in parts)
    if not n_tr:
        raise RootCanalError("None of these events had a max-amp contact to "
                             "average.")
    mean = sum(q["tr_sum"] for q in parts) / n_tr
    sq = sum(q["tr_sq"] for q in parts) / n_tr
    sd = np.sqrt(np.clip(sq - mean * mean, 0.0, None))
    pol, mres = _best_polarity(mean, c, fs, p)
    mres = mres or {}
    flipped = sum(q["flipped"] for q in parts)
    w_main = max(main["rows_hit"], key=main["rows_hit"].get) \
        if main["rows_hit"] else 0
    trace = {
        "t_ms": [float(v) for v in t_ms],
        "y": [_f(v) for v in mean[idx]],
        "sd": [_f(v) for v in sd[idx]],
        "baseline": _f(mres.get("baseline_uV", np.nan)),
        "peak_ms": _f(mres.get("peak_ms", np.nan)),
        "peak_uV": _f(mres.get("signed_peak_uV", np.nan)),
        "left_ms": _f(mres.get("left_ms", np.nan)),
        "right_ms": _f(mres.get("right_ms", np.nan)),
        "half_uV": _f(mres.get("half_level_uV", np.nan)),
        "amp_uV": _f(mres.get("amp_uV", np.nan)),
        "hw_ms": _f(mres.get("hw_ms", np.nan)),
        "unresolved": bool(mres.get("unresolved")),
        "contact": nums[w_main], "contact_row": w_main, "polarity": pol,
        "n": n_tr, "flipped": flipped,
        "each_own_contact": True,
    }

    n_sp = sum(q["n_sp"] for q in parts)
    pe = sum(q["pe_sum"] for q in parts if q["pe_sum"] is not None)
    pb = sum(q["pb_sum"] for q in parts if q["pb_sum"] is not None)
    spectrum = None
    if n_sp:
        spectrum = {"f": [float(v) for v in main["f"]],
                    "event": [_f(v) for v in pe / n_sp],
                    "baseline": [_f(v) for v in pb / n_sp],
                    "band": [float(p.band_lo), float(p.band_hi)],
                    "contact": None, "n": n_sp}
        with np.errstate(divide="ignore", invalid="ignore"):
            spectrum["db"] = _db_s_num(_band_power(main["f"], pe / n_sp,
                                                   p.band_lo, p.band_hi),
                                       _band_power(main["f"], pb / n_sp,
                                                   p.band_lo, p.band_hi))

    bad = _bad_rows(got)
    have = main["raw_n"] > 0
    raw_mean = np.where(have[:, None],
                        main["raw_sum"] / np.maximum(main["raw_n"], 1)[:, None],
                        np.nan)
    st = np.full_like(raw_mean, np.nan)
    if have.any():
        st[have] = _filter(raw_mean[have], p, fs)
    wave = st[:, idx]
    good = ~bad & have
    g = 4.0
    scale = (float(np.percentile(np.abs(wave[good]), 99.5))
             if good.any() else 1.0) or 1.0
    stack = {"t_ms": [float(v) for v in t_ms],
             "rows": [[_f(v) for v in (-wave[k] * g / scale)]
                      for k in range(len(nums))],
             "nums": nums, "bad": [bool(b) for b in bad], "gain": g,
             "uv_per_contact": float(scale / g), "contact": nums[w_main],
             "n": main["n"]}
    st = [[_f(v) for v in r_] for r_ in stack["rows"]]
    stack["rows"] = st

    runs = got.get("runs") or [{"rows": list(range(len(nums))),
                                "numbers": nums}]
    run = next((ru for ru in runs if w_main in ru["rows"]), runs[0])
    rows = list(run["rows"])
    chans = [{"number": nums[k]} for k in rows]
    lfp = _ds_filter(np.nan_to_num(raw_mean[rows]), fs)[:, idx]
    lfp = braces.repair(lfp, chans, {nums[k]: "bad" for k in rows if bad[k]})
    dp = dspca.Params(probe=got.get("probe"))
    csd = dspca.toothy_csd(lfp, float(got.get("spacing_um") or 50.0), dp)[1]
    lim = float(np.percentile(np.abs(csd), 99)) or 1.0
    out_csd = {"t_ms": [float(v) for v in t_ms],
               "rows": [[float(v) for v in r_] for r_ in csd],
               "nums": [nums[k] for k in rows], "clim": [-lim, lim],
               "unit": "A/m³", "contact": nums[w_main],
               "filter": "%g–%g Hz, %g Hz mains taken out (the dentate-"
                         "spike band)" % (CSD_BAND[0], CSD_BAND[1],
                                          CSD_LINE_HZ),
               "band": [float(CSD_BAND[0]), float(CSD_BAND[1])],
               "notch_hz": float(CSD_LINE_HZ), "n": main["n"]}
    return {"group": True, "label": label, "n": sum(q["n"] for q in parts),
            "n_reads": len(parts), "probe_from_n": main["n"],
            "trace": trace, "spectrum": spectrum, "stack": stack,
            "csd": out_csd, "filter": [float(p.lo_hz), float(p.hi_hz)],
            "filt": p.filt, "mains_out": bool(p.mains_out),
            "filter_label": p.filter_label()}


def _db_s_num(a, b):
    try:
        return float(10.0 * np.log10(a / b)) if a > 0 and b > 0 else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def event_view(got, p, i):
    """Everything the click panel draws for event `i`, as arrays.

    The measurement is recomputed for this one event from the same snippet
    with the same filter -- rows are filtered independently, so it is the
    fit's number exactly, not a second opinion.
    """
    snip = got["snip"]
    n_ev, n_ch, n_t = snip.shape
    if not 0 <= int(i) < n_ev:
        raise RootCanalError("There is no event %s in this read (it has %d)."
                             % (i, n_ev))
    i = int(i)
    _check_cross(got, p)
    fs = float(got["snip_fs"])
    nums = [int(v) for v in got["nums"]]
    yf = _filter(snip[i], p, fs)                         # [ch x T]
    if not np.isfinite(yf).any():
        raise RootCanalError(
            "Event %d could not be read from the recording, so there is "
            "nothing to show for it." % (i + 1))
    bad = _bad_rows(got)
    c = (n_t - 1) // 2
    h = int(round(p.win_ms * 1e-3 * fs))
    dev = _pick(yf, bad, c, h)
    w = int(np.argmax(dev))
    pol, mres = _best_polarity(yf[w], c, fs, p)
    mres = mres or {}
    if (i in p.retry and mres.get("status") == "ok"
            and not np.isfinite(mres.get("hw_ms", np.nan))):
        m2 = measure_peak(yf[w], c, fs, pol, p.win_ms, retry_cross_ms(got),
                          p.flank_ms)
        if m2 and m2.get("status") == "ok" and np.isfinite(m2["hw_ms"]):
            mres = m2
    idx, _c = _display_idx(n_t, fs)
    t_ms = (idx - c) / fs * 1e3

    trace = {
        "t_ms": [float(v) for v in t_ms],
        "y": [_f(v) for v in yf[w, idx]],
        "baseline": _f(mres.get("baseline_uV", np.nan)),
        "peak_ms": _f(mres.get("peak_ms", np.nan)),
        "peak_uV": _f(mres.get("signed_peak_uV", np.nan)),
        "left_ms": _f(mres.get("left_ms", np.nan)),
        "right_ms": _f(mres.get("right_ms", np.nan)),
        "half_uV": _f(mres.get("half_level_uV", np.nan)),
        "amp_uV": _f(mres.get("amp_uV", np.nan)),
        "hw_ms": _f(mres.get("hw_ms", np.nan)),
        "unresolved": bool(mres.get("unresolved")),
        "contact": nums[w], "contact_row": w,
        "polarity": pol,
    }

    # The spectrum on the contact the HF number came from, which is the one
    # that makes the number checkable. The baseline was taken over a shorter
    # window and so sits on a coarser grid; it is interpolated onto the
    # event's, which moves no power between bands that matter here.
    D, best, brow = hf_db(got, p)
    r = int(brow[i]) if brow[i] >= 0 else w
    fe, fb = np.asarray(got["f_ev"]), np.asarray(got["f_base"])
    pe = np.asarray(got["psd_ev"][i, r], dtype=np.float64)
    pb = np.interp(fe, fb, np.asarray(got["psd_base"][i, r], dtype=np.float64))
    spectrum = {"f": [float(v) for v in fe],
                "event": [_f(v) for v in pe],
                "baseline": [_f(v) for v in pb],
                "band": [float(p.band_lo), float(p.band_hi)],
                "contact": nums[r], "db": _f(best[i])}

    # The stack: every contact, in contact units, as X-ray's traces pane
    # draws them -- the browser draws `row - value`.
    wave = yf[:, idx]
    g = 4.0
    good = ~bad & np.isfinite(wave).all(axis=1)
    scale = (float(np.percentile(np.abs(wave[good]), 99.5))
             if good.any() else 1.0) or 1.0
    stack = {"t_ms": [float(v) for v in t_ms],
             "rows": [[_f(v) for v in (-wave[k] * g / scale)]
                      for k in range(n_ch)],
             "nums": nums,
             "bad": [bool(b) for b in bad],
             "gain": g,
             "uv_per_contact": float(scale / g),
             "contact": nums[w]}

    # The CSD down the column the max contact is in, on the DENTATE-SPIKE
    # filter (see `_ds_filter`), not the fit filter. Bad contacts are
    # repaired from their neighbours rather than dropped, for the reason
    # `braces.repair` gives: a second difference needs an even grid.
    runs = got.get("runs") or [{"rows": list(range(n_ch)), "numbers": nums}]
    run = next((ru for ru in runs if w in ru["rows"]), runs[0])
    rows = list(run["rows"])
    chans = [{"number": nums[k]} for k in rows]
    lfp = _ds_filter(snip[i][rows], fs)[:, idx]
    lfp = braces.repair(lfp, chans, {nums[k]: "bad" for k in rows if bad[k]})
    dp = dspca.Params(probe=got.get("probe"))
    csd = dspca.toothy_csd(lfp, float(got.get("spacing_um") or 50.0), dp)[1]
    lim = float(np.percentile(np.abs(csd), 99)) or 1.0
    out_csd = {"t_ms": [float(v) for v in t_ms],
               "rows": [[float(v) for v in r_] for r_ in csd],
               "nums": [nums[k] for k in rows],
               "clim": [-lim, lim],
               "unit": "A/m³",
               "contact": nums[w],
               "filter": "%g–%g Hz, %g Hz mains taken out (the dentate-"
                         "spike band)"
                         % (CSD_BAND[0], CSD_BAND[1], CSD_LINE_HZ),
               "band": [float(CSD_BAND[0]), float(CSD_BAND[1])],
               "notch_hz": float(CSD_LINE_HZ)}

    return {"i": i, "t": float(got["t"][i]),
            "trace": trace, "spectrum": spectrum, "stack": stack,
            "csd": out_csd,
            "filter": [float(p.lo_hz), float(p.hi_hz)],
            "filt": p.filt, "mains_out": bool(p.mains_out),
            "filter_label": p.filter_label()}
