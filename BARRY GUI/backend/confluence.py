# -*- coding: utf-8 -*-
"""The Confluence -- Incisor's dentate spikes and Doppler's discharges, pooled.

Two detectors look at one recording for two different things, and some of
what each finds is the other's: an IED under a dentate-spike detector is a
large, fast, sharp event, and a big dentate spike can cross a line-length
threshold. Pooling them gives one list to sort (Panning), line up (Lock) and
tease apart in Root Canal's three-axis space, where Incisor's and Doppler's
events can be seen side by side.

THE RULE (decided with the user, 2026-10-14)
    * Time only, any channel. A dentate spike on the hilus and an IED on
      seven channels three milliseconds apart are one event.
    * Within a window, 5 ms by default and adjustable.
    * One to one, nearest first: each Incisor event pairs with at most one
      Doppler event and the other way about, closest pairs first, so a
      burst of three IEDs near one dentate spike merges the nearest and
      leaves the other two as Doppler's own.
    * A merged event keeps INCISOR's time -- a dentate-spike detector stamps
      the spike's own peak, sample-precise -- and `pair_t` keeps Doppler's,
      so nothing is lost and the gap can always be read back.

WHAT GOES IN
A banked entry's events at one version. Anything already called Garbage --
in Checkup or in Spotter -- stays out: somebody has looked at it and said it
is not an event, and pooling it again would be asking the same question
twice. Undecided, flagged and confirmed events all go in.
"""
from __future__ import annotations

import bisect

DEFAULT_WINDOW_MS = 5.0
MAX_WINDOW_MS = 100.0
ORIGINS = ("incisor", "doppler", "both")


def window_s(ms):
    """The window in seconds, from milliseconds, refusing nonsense."""
    try:
        v = float(ms)
    except (TypeError, ValueError):
        v = DEFAULT_WINDOW_MS
    if not (v > 0):
        raise ValueError("The merge window has to be longer than 0 ms.")
    if v > MAX_WINDOW_MS:
        raise ValueError("A merge window over %d ms would join events that "
                         "are not the same event." % MAX_WINDOW_MS)
    return v / 1000.0


def usable(events, vocab):
    """The events that go into a pool: everything except what has been
    called a non-event. `vocab` is the curation vocabulary of the entry's
    kind; a label is a non-event when it is in the vocabulary and is
    neither `good` nor `flagged` (Garbage, in both of them)."""
    bad = set()
    for lab in (vocab or []):
        if not lab.get("good") and not lab.get("flagged"):
            bad.add(str(lab.get("id")).lower())
            bad.add(str(lab.get("name")).lower())
    out = []
    for e in (events or []):
        lab = e.get("label_id") or e.get("label")
        if lab and str(lab).lower() in bad:
            continue
        try:
            t = float(e.get("start"))
        except (TypeError, ValueError):
            continue
        out.append(dict(e, start=t))
    out.sort(key=lambda e: e["start"])
    return out


def pool(ds, ied, win_s):
    """Pool two sorted lists of events. Returns (events, stats).

    `ds` and `ied` are dicts with at least `start`. Every output event is
    {start, origin, pair_t?, dt_ms?, channel?, amplitude?, ds?, ied?} where
    `ds`/`ied` are the indices of the events it came from.
    """
    dt = [float(e["start"]) for e in ds]
    it = [float(e["start"]) for e in ied]
    # Every candidate pair within the window, nearest first.
    pairs = []
    for j, t in enumerate(it):
        lo = bisect.bisect_left(dt, t - win_s)
        hi = bisect.bisect_right(dt, t + win_s)
        for i in range(lo, hi):
            pairs.append((abs(dt[i] - t), i, j))
    pairs.sort()
    used_d, used_i, match = set(), set(), {}
    for d, i, j in pairs:
        if i in used_d or j in used_i:
            continue
        used_d.add(i)
        used_i.add(j)
        match[i] = j
    out = []
    for i, e in enumerate(ds):
        row = {"start": round(float(e["start"]), 6), "ds": i}
        for k in ("channel", "amplitude"):
            if e.get(k) is not None:
                row[k] = e[k]
        if i in match:
            j = match[i]
            o = ied[j]
            row["origin"] = "both"
            row["ied"] = j
            row["pair_t"] = round(float(o["start"]), 6)
            row["dt_ms"] = round((float(o["start"]) - float(e["start"])) * 1e3, 3)
            if row.get("channel") is None and o.get("channel") is not None:
                row["channel"] = o["channel"]
        else:
            row["origin"] = "incisor"
        out.append(row)
    for j, o in enumerate(ied):
        if j in used_i:
            continue
        row = {"start": round(float(o["start"]), 6), "origin": "doppler",
               "ied": j}
        for k in ("channel", "amplitude"):
            if o.get(k) is not None:
                row[k] = o[k]
        out.append(row)
    out.sort(key=lambda r: r["start"])
    both = sum(1 for r in out if r["origin"] == "both")
    stats = {
        "n_ds": len(ds), "n_ied": len(ied), "n": len(out),
        "merged": both,
        "incisor_only": len(ds) - both,
        "doppler_only": len(ied) - both,
        "window_ms": round(win_s * 1e3, 3),
        "dt_ms": sorted(r["dt_ms"] for r in out if "dt_ms" in r),
    }
    return out, stats
