"""
ied_ampwidth.py -- amplitude and half-width of an IED, measured honestly.

WHAT THIS REPLACES, AND WHY
===========================
`IED/05_Session_Pipeline/components/EventStacks_AmpWidth.m` already measures an
amplitude and a half-width per channel. It does three things that this does
not, and each of them turns a missing measurement into a confident wrong one:

  1. IT MEASURES HALF-AMPLITUDE FROM ZERO.
     `h = 0.5 * amp_uV` where `amp_uV` is the extremum's distance from 0 uV.
     The LFP on this probe sits tens to hundreds of microvolts off zero and
     drifts, so "zero" is not the event's baseline -- it is wherever the
     amplifier happened to be. A trace riding +200 uV high has every crossing
     pushed outward and its half-width inflated; a trace riding low has it cut
     short. Nothing in the output says which happened.

  2. IT HUNTS THE CROSSINGS ONLY INSIDE THE METRIC WINDOW (+-5 ms default).
     The curated events in this session are ~40 ms wide on/off. A crossing
     that never happens inside +-5 ms makes the while-loop walk to the window
     edge, and the code then interpolates off the last pair of samples as if a
     crossing had been found there. A half-width that is really ">10 ms,
     unresolved" is reported as a number near 10 ms.

  3. IT IS BLIND TO THE RAIL.
     This acquisition clips at +-1999.94 uV, and EVERY curated Solid event in
     this session has channels pinned there, in the GCL/hilus rows where the
     IED is largest. "Max amplitude across channels" therefore selects a
     censored channel by construction: the amplitude is a lower bound, the
     peak is a plateau rather than a peak, and the flat top holds the trace
     above half-amplitude for longer than the event does, so the half-width is
     inflated too. Reported as a plain number, it is indistinguishable from a
     real one.

So the measurements here carry their own provenance. Every channel comes back
with the baseline that was subtracted, whether each crossing was actually
found or the search ran out of window, and how many samples of the half-width
span sat on the rail. A caller that ignores the flags gets the MATLAB answer;
a caller that honours them knows which numbers are measurements.

THE THREE BASELINES, AND WHY THE CHOICE IS THE WHOLE QUESTION
=============================================================
"Half-width" is the width at half of *something*, and the something is a
baseline. The three defensible choices disagree with each other by more than
the noise, so this exposes all three rather than picking one silently:

  zero        half of the distance from 0 uV.  What the MATLAB does. Kept so
              old numbers can be reproduced, not because it is right.
  local       half of the distance from the median of two flanking windows
              (default 30-60 ms either side, outside the event). This is the
              "what was the trace doing before the event" answer.
  prominence  half of the distance down to the higher of the two flanking
              minima -- scipy's peak_widths(rel_height=0.5). Needs no baseline
              estimate and no assumption that the flanks are quiet, but on a
              biphasic event it measures the spike riding on the slow wave
              rather than the whole deflection.

`local` is the default because these events sit on a visibly drifting field.
Whichever is used is recorded in the output row.

MEASURED, NOT DRAWN
===================
The stack you look at and the numbers are computed from the same trace, but
the measurement filter is a stated setting, not a side effect of plotting.
30 kHz broadband carries unit spikes that can win a "largest deflection"
search outright, so the default lowpasses at 300 Hz for measurement. Turn it
off and you measure the broadband, which is what the MATLAB does.
"""
from __future__ import annotations

import glob
import os
import re

import numpy as np
import pandas as pd
from scipy.signal import butter, iirnotch, sosfiltfilt, filtfilt

# The acquisition's clip level. Measured, not assumed: the largest magnitude
# anywhere in the curated events is 1999.93896484375 uV and it recurs on
# thousands of samples, which is a rail and not a coincidence.
RAIL_UV = 1999.5

DEFAULT_MAT = (r"C:\Users\Z390\Desktop\IED DATA\Take 3\PTEN_M13_pten_m13s2aug1"
               r"\LL_input_2023-08-01_12-11-26_mex_disk_uV (4).mat")
DEFAULT_XLS = (r"C:\Users\Z390\Desktop\IED DATA\Take 3\PTEN_M13_pten_m13s2aug1"
               r"\ets_converted_events.xlsx")
DEFAULT_ANAT = (r"C:\Users\Z390\Desktop\IED DATA\Take 3\PTEN_M13_pten_m13s2aug1"
                r"\m13s2_anatomical_detail.csv")
DEFAULT_ROOT = r"C:\Users\Z390\Desktop\IED DATA\Take 3\PTEN_M13_pten_m13s2aug1"

# Curation folders hold one PNG per event, named Evt###_...
CATEGORIES = ("Solid", "Sputter", "Flag", "Garbage")

BASELINES = ("local", "zero", "prominence")


# --------------------------------------------------------------------------
# The event table and its curation labels
# --------------------------------------------------------------------------
def read_events(xls_path=DEFAULT_XLS, root=DEFAULT_ROOT):
    """The on/off table, with each event's curation folder attached.

    Event numbering is 1-based and matches the PNG names: EventStacks_AmpWidth
    writes `Evt%03d` from its 1-based loop index over the spreadsheet rows, so
    Evt010 is row 10 of the sheet. Nothing renumbers in between.
    """
    tab = pd.read_excel(xls_path)
    cols = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in tab.columns}
    on = cols.get("onsamp") or cols.get("startsample") or tab.columns[0]
    off = cols.get("offsamp") or cols.get("endsample") or tab.columns[1]
    ev = pd.DataFrame({
        "evt": np.arange(1, len(tab) + 1, dtype=int),
        "on_samp": tab[on].astype(np.int64).values,
        "off_samp": tab[off].astype(np.int64).values,
    })
    # An event can be filed in more than one curation folder -- in this
    # session Evt035 and Evt040 sit in BOTH Solid and Sputter. Whichever
    # folder happened to be scanned last used to win, silently, which is how
    # two of the thirteen Solid events disappeared from the Solid set. Every
    # folder an event appears in is kept; `category` takes the first in
    # CATEGORIES order and `filed_in` records the disagreement so it can be
    # settled by whoever curated it rather than by directory order.
    filed = {}
    for cat in CATEGORIES:
        for png in glob.glob(os.path.join(root, cat, "Evt*.png")):
            m = re.match(r"Evt(\d+)", os.path.basename(png))
            if not m:
                continue
            filed.setdefault(int(m.group(1)), []).append(cat)

    order = {c: i for i, c in enumerate(CATEGORIES)}
    cats, filed_in = [], []
    for n in ev["evt"]:
        got = sorted(set(filed.get(int(n), [])), key=lambda c: order[c])
        cats.append(got[0] if got else "uncurated")
        filed_in.append("|".join(got))
    ev["category"] = cats
    ev["filed_in"] = filed_in
    ev["conflict"] = [len(f.split("|")) > 1 if f else False for f in filed_in]
    return ev


def read_anatomy(path=DEFAULT_ANAT):
    """CSC number -> region label. The CSV's `Row` is the electrode number."""
    try:
        an = pd.read_csv(path)
    except Exception:
        return {}
    return {int(r): str(g) for r, g in zip(an["Row"], an["Region"])}


# --------------------------------------------------------------------------
# The recording
# --------------------------------------------------------------------------
class Recording:
    """Lazy window reads out of the 4.9 GB LL_input .mat.

    The file is HDF5 (MATLAB v7.3) and stores `d` transposed, so on the Python
    side it is (samples, channels) and a time window is one contiguous slab --
    a few milliseconds to read. Nothing here loads the whole recording, which
    is the only reason a GUI over a 31-minute 32-channel session is usable.
    """

    def __init__(self, mat_path=DEFAULT_MAT, anat_path=DEFAULT_ANAT):
        import h5py
        self.path = mat_path
        self._f = h5py.File(mat_path, "r")
        self.d = self._f["d"]
        self.n_samp, self.n_ch = self.d.shape
        self.sfx = float(np.asarray(self._f["sfx"]).ravel()[0])
        self.kept = np.asarray(self._f["kept_channels"]).ravel().astype(int)
        self.region = read_anatomy(anat_path)
        self.dur_s = self.n_samp / self.sfx

    def label(self, row):
        """Row index -> 'CSC26 DG GCL1'."""
        csc = int(self.kept[row]) if row < len(self.kept) else row + 1
        reg = self.region.get(csc, "")
        return "CSC%d %s" % (csc, reg) if reg else "CSC%d" % csc

    def csc(self, row):
        return int(self.kept[row]) if row < len(self.kept) else row + 1

    def window(self, center, half_samp):
        """(data[T, nCh], t0) around `center`, clipped to the recording."""
        s0 = int(max(0, center - half_samp))
        s1 = int(min(self.n_samp, center + half_samp + 1))
        return np.asarray(self.d[s0:s1, :], dtype=float), s0

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Measurement filter
# --------------------------------------------------------------------------
def prep(seg, sfx, lowpass=300.0, notch=None):
    """The trace the numbers come off.

    Broadband at 30 kHz carries unit spikes an order of magnitude narrower
    than an IED; a "largest deflection" search over raw samples can be won by
    one of them, and that pick is not an IED amplitude. Lowpass is therefore
    ON by default and stated in every output row.

    The notch is off by default because it is not free: 60 Hz sits inside the
    band an IED occupies, so notching reshapes the event a little as well as
    the line. It is here for recordings where the line is large enough that
    half-amplitude crossings land on a mains ripple instead of on the event.
    """
    y = np.asarray(seg, dtype=float)
    if notch:
        b, a = iirnotch(float(notch), 30.0, sfx)
        y = filtfilt(b, a, y, axis=0)
    if lowpass:
        nyq = sfx / 2.0
        wn = min(float(lowpass) / nyq, 0.99)
        sos = butter(4, wn, btype="low", output="sos")
        y = sosfiltfilt(sos, y, axis=0)
    return y


# --------------------------------------------------------------------------
# Half-width
# --------------------------------------------------------------------------
def _cross(y, pk, level, direction, lo, hi):
    """Walk out from `pk` to where `y` falls through `level`.

    Returns (index_float, edge_limited). `edge_limited` is the flag the MATLAB
    does not have: True means the trace never came back below half-amplitude
    before the search window ran out, so there IS no crossing to interpolate
    and the half-width is a lower bound, not a value. The old code walks to
    the edge and interpolates off the final sample pair regardless, which
    turns "unresolved" into a plausible-looking number.
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


def _baseline(y, anchor, sfx, mode, flank_ms, pk, lo, hi):
    """The level half-amplitude is measured down to. See module docstring."""
    if mode == "zero":
        return 0.0
    if mode == "prominence":
        # Higher of the two flanking minima -- scipy peak_widths(rel_height=.5).
        left = np.min(y[lo:pk + 1]) if pk > lo else y[pk]
        right = np.min(y[pk:hi + 1]) if pk < hi else y[pk]
        return float(max(left, right))
    # "local": the quiet field either side of the event.
    f0 = int(round(flank_ms[0] * 1e-3 * sfx))
    f1 = int(round(flank_ms[1] * 1e-3 * sfx))
    n = len(y)
    picks = []
    a0, a1 = anchor - f1, anchor - f0
    if a1 > 0:
        picks.append(y[max(0, a0):max(1, a1)])
    b0, b1 = anchor + f0, anchor + f1
    if b0 < n:
        picks.append(y[min(n - 1, b0):min(n, b1)])
    picks = [p for p in picks if p.size]
    if not picks:
        return float(np.median(y))
    return float(np.median(np.concatenate(picks)))


def measure_peak(y, anchor, sfx, polarity, peak_ms, cross_ms, baseline,
                 flank_ms=(30.0, 60.0), raw=None):
    """Amplitude and half-width of one polarity on one channel.

    `y` is the (filtered) trace, `anchor` the sample index of the midline the
    user placed. The extremum is taken inside +-`peak_ms` of the midline; the
    half-amplitude crossings are hunted inside the wider +-`cross_ms`, because
    an event whose crossings fall outside the peak-search window still has a
    half-width and clamping the search to the peak window is what makes the
    old measurement top out.

    `raw` -- the unfiltered trace, if the rail is to be detected on the trace
    that actually clipped. Filtering rounds a plateau's corners, so clipping
    must be read off the raw samples or it is missed.
    """
    n = len(y)
    sgn = 1.0 if polarity == "max" else -1.0
    s = sgn * np.asarray(y, dtype=float)

    pw = int(round(peak_ms * 1e-3 * sfx))
    cw = int(round(cross_ms * 1e-3 * sfx))
    plo, phi = max(0, anchor - pw), min(n - 1, anchor + pw)
    clo, chi = max(0, anchor - cw), min(n - 1, anchor + cw)
    if phi <= plo:
        return None

    pk = int(plo + np.argmax(s[plo:phi + 1]))
    # Computed in the oriented frame (peak positive) for every mode alike, so
    # the min-polarity pass is the max-polarity pass on a flipped trace and
    # there is no second code path to keep in step.
    base_s = _baseline(s, anchor, sfx, baseline, flank_ms, pk, clo, chi)

    amp = float(s[pk] - base_s)
    base_out = {
        "polarity": polarity,
        "peak_i": pk,
        "peak_ms": (pk - anchor) / sfx * 1e3,
        "amp_uV": amp,
        "signed_peak_uV": float(sgn * s[pk]),
        "baseline_uV": float(sgn * base_s),
    }
    # A channel can genuinely have no deflection of this polarity: on the CA1
    # rows of a hilar discharge the trace never rises above the local baseline
    # at all, so the "most positive" sample is still below it. That is an
    # answer, not a failure, but half of a negative height is not a level any
    # crossing can be found at -- so the width is withheld and the reason is
    # carried in `status`, rather than returning a bare NaN that reads the
    # same as a measurement that broke.
    if not np.isfinite(amp) or amp <= 0:
        base_out.update({
            "status": "no_deflection",
            "half_level_uV": np.nan,
            "left_i": np.nan, "right_i": np.nan,
            "left_ms": np.nan, "right_ms": np.nan,
            "hw_ms": np.nan,
            "edge_left": False, "edge_right": False,
            "unresolved": False,
            "clipped_samples": 0, "peak_at_rail": False,
        })
        return base_out
    level = base_s + 0.5 * amp

    li, l_edge = _cross(s, pk, level, -1, clo, chi)
    ri, r_edge = _cross(s, pk, level, +1, clo, chi)
    hw_ms = (ri - li) / sfx * 1e3 if ri > li else float("nan")

    # Clipping, read off the raw trace across the half-width span.
    clipped_n = 0
    at_rail = False
    if raw is not None:
        a, b = int(np.floor(li)), int(np.ceil(ri)) + 1
        span = np.abs(np.asarray(raw, float)[max(0, a):min(n, b)])
        clipped_n = int((span >= RAIL_UV).sum())
        at_rail = bool(abs(float(raw[pk])) >= RAIL_UV)

    base_out.update({
        "status": "ok",
        "half_level_uV": float(sgn * level),
        "left_i": li, "right_i": ri,
        "left_ms": (li - anchor) / sfx * 1e3,
        "right_ms": (ri - anchor) / sfx * 1e3,
        "hw_ms": hw_ms,
        "edge_left": l_edge, "edge_right": r_edge,
        "unresolved": bool(l_edge or r_edge),
        "clipped_samples": clipped_n,
        "peak_at_rail": at_rail,
    })
    return base_out


def load_window(rec, anchor, half_samp, lowpass=300.0, notch=None):
    """Read and filter once. The expensive half.

    Kept apart from the measuring half because dragging a midline must not
    re-read a 4.9 GB file or re-run a filtfilt over 32 channels: the window
    and its filtered copy depend on the event and the filter settings, not on
    where the midline currently sits.
    """
    raw, s0 = rec.window(anchor, half_samp)
    filt = prep(raw, rec.sfx, lowpass=lowpass, notch=notch)
    return {"raw": raw, "filt": filt, "s0": s0, "sfx": rec.sfx,
            "rail": np.abs(raw).max(axis=0) >= RAIL_UV,
            "lowpass": lowpass, "notch": notch}


def measure_window(ctx, rec, anchor_i, peak_ms=10.0, cross_ms=50.0,
                   baseline="local", flank_ms=(30.0, 60.0)):
    """Every channel, both polarities, around one midline. The cheap half."""
    raw, filt = ctx["raw"], ctx["filt"]
    ai = int(anchor_i)
    rows = []
    for ch in range(rec.n_ch):
        r = {"row": ch, "csc": rec.csc(ch),
             "region": rec.region.get(rec.csc(ch), ""),
             "label": rec.label(ch),
             "any_rail": bool(ctx["rail"][ch])}
        for pol in ("max", "min"):
            r[pol] = measure_peak(filt[:, ch], ai, rec.sfx, pol, peak_ms,
                                  cross_ms, baseline, flank_ms, raw=raw[:, ch])
        rows.append(r)
    return rows


def measure_event(rec, anchor, half_samp, peak_ms=10.0, cross_ms=50.0,
                  baseline="local", flank_ms=(30.0, 60.0),
                  lowpass=300.0, notch=None):
    """Read, filter and measure one event in one call.

    Returns (rows, ctx). `ctx` carries the window itself so a caller draws
    exactly what was measured rather than re-reading and hoping it matches.
    """
    ctx = load_window(rec, anchor, half_samp, lowpass=lowpass, notch=notch)
    ai = int(anchor - ctx["s0"])
    rows = measure_window(ctx, rec, ai, peak_ms, cross_ms, baseline, flank_ms)
    ctx["anchor_i"] = ai
    ctx["anchor"] = anchor
    ctx["settings"] = {"peak_ms": peak_ms, "cross_ms": cross_ms,
                       "baseline": baseline, "lowpass": lowpass,
                       "notch": notch, "flank_ms": flank_ms}
    return rows, ctx


def winner(rows, polarity="abs", exclude_clipped=True):
    """Which channel carries the event.

    `exclude_clipped` is on by default and it is the point of this function.
    Every curated Solid event in this session rails somewhere in the
    GCL/hilus, so an unguarded argmax over |amplitude| returns a channel whose
    true amplitude is unknown and at least 2000 uV -- the same answer for
    every event, carrying no information about any of them. Skipping the
    railed channels reports the largest channel that was actually measured,
    and the caller is still told how many were skipped.
    """
    def one(m):
        # A channel with no deflection of this polarity must not be able to
        # win on the size of its non-deflection.
        return m["amp_uV"] if (m and m.get("status") == "ok") else -np.inf

    def amp(r):
        if polarity == "abs":
            return max(one(r["max"]), one(r["min"]))
        return one(r[polarity])

    pool = rows
    if exclude_clipped:
        clean = [r for r in rows if not r["any_rail"]]
        if clean:
            pool = clean
    best = max(pool, key=amp, default=None)
    return best


def best_polarity(row):
    """'max' or 'min', whichever deflection on this channel is larger."""
    def one(m):
        return m["amp_uV"] if (m and m.get("status") == "ok") else -np.inf
    return "max" if one(row["max"]) >= one(row["min"]) else "min"


# --------------------------------------------------------------------------
# Self test -- run the measurement over the curated Solid events
# --------------------------------------------------------------------------
def _selftest():
    ev = read_events()
    rec = Recording()
    print("recording: %.1f s, %d ch @ %.0f Hz" % (rec.dur_s, rec.n_ch, rec.sfx))
    print("events: %d  (%s)" % (
        len(ev), ", ".join("%s=%d" % (c, (ev["category"] == c).sum())
                           for c in CATEGORIES)))
    solid = ev[ev["category"] == "Solid"]
    half = int(0.080 * rec.sfx)

    print("\n%-7s %-16s %9s %8s %7s   | %s" %
          ("evt", "best clean ch", "amp uV", "HW ms", "pol", "railed rows"))
    for _, e in solid.iterrows():
        anchor = int((e["on_samp"] + e["off_samp"]) // 2)
        rows, _ = measure_event(rec, anchor, half)
        w = winner(rows)
        pol = best_polarity(w)
        m = w[pol]
        nrail = sum(r["any_rail"] for r in rows)
        flag = ""
        if m["unresolved"]:
            flag = " UNRESOLVED"
        print("Evt%03d %-16s %9.1f %8.2f %7s   | %d/%d%s" %
              (e["evt"], w["label"], m["amp_uV"], m["hw_ms"], pol,
               nrail, len(rows), flag))

    # How much does the baseline choice actually move the answer?
    print("\nbaseline comparison on the best clean channel (HW ms):")
    print("%-7s %9s %9s %12s" % ("evt", "local", "zero", "prominence"))
    for _, e in solid.iterrows():
        anchor = int((e["on_samp"] + e["off_samp"]) // 2)
        out = []
        for b in BASELINES:
            rows, _ = measure_event(rec, anchor, half, baseline=b)
            w = winner(rows)
            out.append(w[best_polarity(w)]["hw_ms"])
        print("Evt%03d %9.2f %9.2f %12.2f" % (e["evt"], out[0], out[1], out[2]))

    rec.close()


if __name__ == "__main__":
    _selftest()
