"""The event-first route: free-running hippocampal P300-like events.

The Monolith asks "what changed between Precon1 and Precon4 in these
windows?". This asks it the other way round (the lab meeting, 2026-10-02):
find the events first -- large positive deflections in the dorsal
hippocampus, wherever they fall in the session -- then ask when they happen
relative to the cues, and which other regions moved with them.

Detection, per rat-day, on the cue session (SPC), read from the local
originals (E:, read only) -- whole sessions are too much to page from the
VACC copy:

  1. the hippocampal wire (the lowest-numbered one of the region not marked
     bad, histology permitting), decimated to 1000 Hz as every Monolith
     signal is, mains notched;
  2. band-passed (0.5-15 Hz by default: a 1 Hz edge takes about 40% off a
     300 ms deflection and halves its width -- measured, tools/
     check_events.py), and robust-z'd over the session:
     (x - median) / (1.4826 * MAD), counted over the samples away from the
     rail only;
  3. every positive peak at or above the threshold (z 4), 150-500 ms wide at
     half its height, at least 500 ms after the last; a peak above the
     ceiling (z 15), or within 250 ms of a sample at the rail, is an
     artifact and is dropped.

Timing: each event is placed against the presentation whose ten seconds
before cue 1 to ten seconds after cue 2 contain it -- pre-baseline, cue 1,
cue 2, post-baseline -- or else the inter-trial interval; rates are events
a minute in each, and a peri-stimulus histogram runs from 10 s before cue 1
to 30 s after it.

Coordination: every region's wire, +-1 s around each event (at most 300 of
them), band-passed the same way, averaged; and the same at twice as many
random times in the session (at least 1.5 s from any event) as the control.
A region "moved with" the events when its event-locked average is bigger
(within +-250 ms) than averages of the same number of random times are
(500 draws), and when its 4-12 Hz phase relative to the hippocampus at the
event is more consistent (PLV) than at random times. Descriptive, rat by
rat; pooled over rats as means and counts, never tested.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import warnings

import numpy as np

from . import coupling, lazyimp, nlx
from . import monolith as MO

find_peaks, hilbert = lazyimp.names("scipy.signal", "find_peaks", "hilbert")

FS = coupling.ANALYSIS_FS
DEFAULTS = {"region": "Right DHC", "low": 0.5, "high": 15.0, "z": 4.0,
            "zmax": 15.0, "min_ms": 150.0, "max_ms": 500.0,
            "refractory_ms": 500.0}
#: The cue session is read from this long before the first cue 1 to this
#: long after the last cue 2.
PAD_S = 30.0
#: Read in pieces this long (a piece across a break in the clock is lost,
#: so smaller loses less), with this much either side for the filters.
CHUNK_S = 30.0
EDGE_S = 1.0
#: A sample within this share of full scale is at the rail.
RAIL_FRAC = 0.995
#: Around a sample at the rail, this much is not trusted.
RAIL_GUARD_S = 0.25
SNIP_S = 1.0
SNIP_PAD_S = 0.6
MAX_EVENTS = 300
NULL_PER_EVENT = 2
NULL_GAP_S = 1.5
N_DRAWS = 500
PEAK_WIN_S = 0.25
PLV_BAND = (4.0, 12.0)
PSTH_FROM, PSTH_TO, PSTH_BIN = -10.0, 30.0, 1.0
WINDOWS = ("pre", "cue1", "cue2", "post")
WINDOW_SAY = {"pre": "Pre-baseline", "cue1": "Cue 1", "cue2": "Cue 2",
              "post": "Post-baseline", "iti": "Between presentations"}
#: The detection band's Butterworth order: gentle (2, run both ways), so a
#: 300 ms deflection keeps its shape -- at 4 the 1 Hz edge rings and
#: narrows it.
DETECT_ORDER = 2
#: Every event-locked trace is sent at this rate.
OUT_FS = 100.0
SCHEMA = 1


class EventsError(MO.MonolithError):
    pass


def params_of(raw=None):
    """The detection's settings, checked; anything not given is the
    default."""
    p = dict(DEFAULTS)
    for k, v in (raw or {}).items():
        if k not in DEFAULTS or v in (None, ""):
            continue
        p[k] = v if k == "region" else float(v)
    names = list(coupling.dewey_map())
    if p["region"] not in names:
        raise EventsError("There is no region called %r." % (p["region"],), 400)
    rules = [
        (0.1 <= p["low"] <= 10, "the band's low edge is 0.1 to 10 Hz"),
        (p["low"] + 2 <= p["high"] <= 40, "the band's high edge is 2 Hz above its low one, at most 40 Hz"),
        (2 <= p["z"] <= 10, "the threshold is z 2 to 10"),
        (p["z"] + 1 <= p["zmax"] <= 60, "the ceiling is at least 1 above the threshold, at most 60"),
        (20 <= p["min_ms"] <= 1000, "the narrowest event is 20 to 1000 ms"),
        (p["min_ms"] + 10 <= p["max_ms"] <= 3000, "the widest is at least 10 ms more than the narrowest, at most 3000"),
        (0 <= p["refractory_ms"] <= 5000, "the gap between events is 0 to 5000 ms"),
    ]
    for ok, say in rules:
        if not ok:
            raise EventsError("Those settings cannot be used: %s." % say, 400)
    return p


def digest(p):
    keep = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in sorted(p.items())}
    return hashlib.sha1(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:12]


def cache_dir(p):
    return MO._path("events", digest(p))


def _cache_path(p, rat, day):
    return os.path.join(cache_dir(p), "r%d_%s.json" % (int(rat), day))


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------
def spc_folder(day):
    f = next((x for x in day.get("folders") or [] if x.get("role") == "SPC"), None)
    return (f or {}).get("local")


def wires_for(day, region):
    """The region's wires, best first: none if histology rules it out;
    those marked bad left out."""
    if region in (day.get("blocked") or {}):
        return []
    bad = set(int(c) for c in day.get("bad") or [])
    return [int(c) for c in coupling.dewey_map()[region] if int(c) not in bad]


def _rail_uv(path, meta):
    hdr = nlx.read_header(path)
    admax = nlx._header_float(hdr, "ADMaxValue") or 32767.0
    return RAIL_FRAC * admax * meta["adbitvolts"] * 1e6


def read_span(path, origin, t0, t1, check=None):
    """One channel, continuous, at 1000 Hz from t0 to t1 s: (signal, ok).
    `ok` is False at the rail (and RAIL_GUARD_S around it) and where a piece
    could not be read (a break in the clock); the signal is 0 there."""
    n = int(round((t1 - t0) * FS))
    x = np.zeros(n)
    ok = np.zeros(n, bool)
    guard = int(round(RAIL_GUARD_S * FS))
    a = t0
    while a < t1 - 1e-9:
        if check:
            check()
        b = min(t1, a + CHUNK_S)
        got, meta = coupling._channel_windows(path, [("c", a - EDGE_S, b + EDGE_S)], origin)
        raw = got.get("c")
        i0, i1 = int(round((a - t0) * FS)), int(round((b - t0) * FS))
        if raw is not None and raw.size:
            fs = meta["fs"]
            rail = np.abs(raw) >= _rail_uv(path, meta)
            y, _f = coupling.decimate_to(raw, fs)
            e = int(round(EDGE_S * FS))
            seg = y[e:e + (i1 - i0)]
            m = np.ones(seg.size, bool)
            if rail.any():
                # Each rail sample, at 1000 Hz, widened by the guard either
                # side (one just beyond the piece's edge counts too).
                at = (np.nonzero(rail)[0] / fs * FS).astype(int) - e + guard
                ind = np.zeros(seg.size + 2 * guard, bool)
                ind[at[(at >= 0) & (at < ind.size)]] = True
                wide = np.convolve(ind.astype(float), np.ones(2 * guard + 1), "same") > 0.5
                m = ~wide[guard:guard + seg.size]
            x[i0:i0 + seg.size] = seg
            ok[i0:i0 + seg.size] = m
        a = b
    x[~ok] = 0.0
    return x, ok


def read_snippets(path, origin, times, half=SNIP_S, check=None):
    """+-`half` s of one channel around each time, at 1000 Hz, notched:
    (n, 2*half*FS+1) with NaN rows where it could not be read or touched
    the rail."""
    m = int(round(half * FS))
    out = np.full((len(times), 2 * m + 1), np.nan)
    rail_uv = None
    for k0 in range(0, len(times), 40):
        if check:
            check()
        part = times[k0:k0 + 40]
        wins = [("s%d" % (k0 + j), float(t) - half - SNIP_PAD_S, float(t) + half + SNIP_PAD_S)
                for j, t in enumerate(part)]
        got, meta = coupling._channel_windows(path, wins, origin)
        for j, t in enumerate(part):
            raw = got.get("s%d" % (k0 + j))
            if raw is None or not raw.size:
                continue
            if rail_uv is None:
                rail_uv = _rail_uv(path, meta)
            fs = meta["fs"]
            p = int(round(SNIP_PAD_S * fs))
            if (np.abs(raw[p:raw.size - p]) >= rail_uv).any():
                continue
            y, _f = coupling.decimate_to(raw, fs)
            y, _l = coupling.notch(y, FS)
            e = int(round(SNIP_PAD_S * FS))
            seg = y[e:e + 2 * m + 1]
            if seg.size == 2 * m + 1:
                out[k0 + j] = seg
    return out


# --------------------------------------------------------------------------
# Detecting
# --------------------------------------------------------------------------
def detect(x, ok, p, t0=0.0):
    """Events in one continuous signal (1000 Hz): [{t, z, width_ms}], and
    the robust centre and spread used."""
    y, _l = coupling.notch(x, FS)
    y = coupling.bandpass(y, FS, p["low"], p["high"], order=DETECT_ORDER)
    good = ok.copy()
    if not good.any():
        return [], None, None
    med = float(np.median(y[good]))
    mad = float(np.median(np.abs(y[good] - med))) * 1.4826
    if not mad > 0:
        return [], med, mad
    z = (y - med) / mad
    z[~good] = 0.0
    dist = max(1, int(round(p["refractory_ms"] / 1000.0 * FS)))
    pk, _props = find_peaks(z, height=p["z"], distance=dist)
    guard = int(round(RAIL_GUARD_S * FS))
    reach = int(round(p["max_ms"] / 1000.0 * FS)) + 1
    bad = ~good
    out = []
    for k in pk:
        if z[k] > p["zmax"]:
            continue
        lo, hi = max(0, k - guard), min(z.size, k + guard + 1)
        if bad[lo:hi].any():
            continue
        # Width: how long the deflection stays above half its height (above
        # the session's centre, not above the troughs beside it -- a slower
        # wave riding under it must not make it look narrower or wider).
        a, b = max(0, k - reach), min(z.size, k + reach + 1)
        below = z[a:b] <= z[k] / 2.0
        left = np.nonzero(below[:k - a])[0]
        right = np.nonzero(below[k - a:])[0]
        if not left.size or not right.size:
            continue                      # wider than the widest allowed
        w_ms = (right[0] - (left[-1] - (k - a)) - 1) / FS * 1000.0
        if not p["min_ms"] <= w_ms <= p["max_ms"]:
            continue
        out.append({"t": round(t0 + k / FS, 4), "z": round(float(z[k]), 3),
                    "width_ms": round(float(w_ms), 1)})
    return out, med, mad


def place(events, units, span):
    """Each event against the presentations: its window, and a
    peri-stimulus histogram re cue 1; rates a minute."""
    t0, t1 = span
    edges = np.arange(PSTH_FROM, PSTH_TO + 1e-9, PSTH_BIN)
    psth = np.zeros(edges.size - 1)
    counts = {w: 0 for w in WINDOWS + ("iti",)}
    secs = {w: 0.0 for w in WINDOWS}
    spans = []
    for u in units:
        pr = u.get("pair") or {}
        a, b, c = pr.get("opener_t"), pr.get("closer_t"), pr.get("offset_t")
        if a is None or b is None or c is None:
            continue
        w = {"pre": (a - 10.0, a), "cue1": (a, b), "cue2": (b, c), "post": (c, c + 10.0)}
        spans.append((a, w))
        for k, (x0, x1) in w.items():
            secs[k] += x1 - x0
    covered = sum(s[1]["post"][1] - s[1]["pre"][0] for s in spans)
    iti_s = max(0.0, (t1 - t0) - covered)
    placed = []
    for ev in events:
        t = ev["t"]
        where, rel = "iti", None
        for a, w in spans:
            if w["pre"][0] <= t < w["post"][1]:
                rel = t - a
                where = next(k for k, (x0, x1) in w.items() if x0 <= t < x1)
                break
        counts[where] += 1
        near = [t - a for a, _w in spans if PSTH_FROM <= t - a < PSTH_TO]
        for r in near:
            psth[int((r - PSTH_FROM) // PSTH_BIN)] += 1
        placed.append(dict(ev, where=where, rel=None if rel is None else round(rel, 3)))
    n_pres = len(spans)
    rate = {w: (60.0 * counts[w] / secs[w] if secs[w] > 0 else None) for w in WINDOWS}
    rate["iti"] = 60.0 * counts["iti"] / iti_s if iti_s > 0 else None
    psth_rate = (60.0 * psth / (n_pres * PSTH_BIN)).tolist() if n_pres else None
    return placed, {"counts": counts, "rate_per_min": rate, "seconds": dict(secs, iti=iti_s),
                    "n_presentations": n_pres,
                    "psth": {"from": PSTH_FROM, "to": PSTH_TO, "bin": PSTH_BIN,
                             "rate_per_min": psth_rate}}


# --------------------------------------------------------------------------
# Coordination
# --------------------------------------------------------------------------
def _band(Y, low, high):
    good = np.isfinite(Y).all(axis=1)
    out = np.full(Y.shape, np.nan)
    if good.any():
        out[good] = coupling.bandpass(Y[good], FS, low, high)
    return out


def _peak(mean, m):
    w = int(round(PEAK_WIN_S * FS))
    return float(np.nanmax(np.abs(mean[m - w:m + w + 1])))


def _thin(v):
    step = int(round(FS / OUT_FS))
    return [None if not np.isfinite(x) else round(float(x), 3) for x in v[::step]]


def coordination(E, N, ref_E, ref_N, p, rng):
    """One region against the events: event-locked average and the
    random-time control, a size index and a phase index, each against
    N_DRAWS same-sized draws of the random times."""
    m = (E.shape[1] - 1) // 2
    Eb, Nb = _band(E, p["low"], p["high"]), _band(N, p["low"], p["high"])
    e_ok = np.isfinite(Eb).all(axis=1)
    n_ok = np.isfinite(Nb).all(axis=1)
    n_e, n_n = int(e_ok.sum()), int(n_ok.sum())
    out = {"n_events": n_e, "n_random": n_n}
    if n_e < 5 or n_n < n_e:
        out["why"] = "too few events or random times with this wire readable"
        return out
    Ee, Nn = Eb[e_ok], Nb[n_ok]
    erp = Ee.mean(axis=0)
    nul = Nn.mean(axis=0)
    obs = _peak(erp, m)
    draws = np.empty(N_DRAWS)
    for k in range(N_DRAWS):
        idx = rng.choice(n_n, n_e, replace=False)
        draws[k] = _peak(Nn[idx].mean(axis=0), m)
    sd = float(draws.std()) or float("nan")
    out.update(erp=_thin(erp), random=_thin(nul),
               random_se=_thin(Nn.std(axis=0) / math.sqrt(n_e)),
               peak=round(obs, 3), peak_random=round(float(draws.mean()), 3),
               z_size=round((obs - float(draws.mean())) / sd, 3) if sd == sd else None,
               p_size=round(float((1 + (draws >= obs).sum()) / (N_DRAWS + 1)), 4))
    # Phase: 4-12 Hz, the region against the hippocampus, at the event.
    if ref_E is not None:
        both_e = e_ok & np.isfinite(ref_E).all(axis=1)
        both_n = n_ok & np.isfinite(ref_N).all(axis=1)
        if both_e.sum() >= 5 and both_n.sum() >= both_e.sum():
            def dphi(A, B):
                a = np.angle(hilbert(_band(A, *PLV_BAND), axis=1)[:, m])
                b = np.angle(hilbert(_band(B, *PLV_BAND), axis=1)[:, m])
                return a - b
            de = dphi(E[both_e], ref_E[both_e])
            dn = dphi(N[both_n], ref_N[both_n])
            plv = float(np.abs(np.exp(1j * de).mean()))
            k_e = int(both_e.sum())
            pd = np.empty(N_DRAWS)
            for k in range(N_DRAWS):
                idx = rng.choice(dn.size, k_e, replace=False)
                pd[k] = np.abs(np.exp(1j * dn[idx]).mean())
            s2 = float(pd.std()) or float("nan")
            out.update(plv=round(plv, 4), plv_random=round(float(pd.mean()), 4),
                       z_plv=round((plv - float(pd.mean())) / s2, 3) if s2 == s2 else None,
                       p_plv=round(float((1 + (pd >= plv).sum()) / (N_DRAWS + 1)), 4))
    return out


# --------------------------------------------------------------------------
# One rat-day, and all of them
# --------------------------------------------------------------------------
def run_day(day, p, check=None, say=None):
    """Everything for one rat-day: the events, their timing, and every
    region's coordination with them."""
    say = say or (lambda *a: None)
    folder = spc_folder(day)
    out = {"schema": SCHEMA, "rat": int(day["rat"]), "day": day["day"], "params": p,
           "at": MO.now_iso()}
    if not folder or not os.path.isdir(folder):
        out["why"] = "the cue session's folder is not on this computer (%s)" % (folder,)
        return out
    origin = nlx.recording_start_us(folder)
    files = dict(nlx.list_csc_files(folder))
    units = day.get("units") or []
    times = [t for u in units for t in ((u.get("pair") or {}).get("opener_t"),
                                         (u.get("pair") or {}).get("offset_t")) if t is not None]
    if origin is None or not times:
        out["why"] = "no clock, or no presentations, in this session"
        return out
    span = (max(0.0, min(times) - 10.0 - PAD_S), max(times) + 10.0 + PAD_S)
    out["span"] = [round(span[0], 3), round(span[1], 3)]
    # The hippocampal wire: the first that reads with under a fifth at the rail.
    wire, x, ok = None, None, None
    for c in wires_for(day, p["region"]):
        if c not in files:
            continue
        say("reading %s (CSC%d)" % (p["region"], c))
        x, ok = read_span(files[c], origin, span[0], span[1], check=check)
        if ok.mean() >= 0.8:
            wire = c
            break
    if wire is None:
        out["why"] = "no wire of %s reads cleanly in this session" % p["region"]
        return out
    say("finding events")
    events, med, mad = detect(x, ok, p, t0=span[0])
    placed, timing = place(events, units, span)
    out.update(wire=wire, centre_uv=med, spread_uv=mad, usable_s=round(float(ok.sum()) / FS, 1),
               events=placed, timing=timing)
    # Coordination: every region at the events and at random times.
    rng = np.random.default_rng(int(day["rat"]) * 1000 + (4 if day["day"].endswith("4") else 1))
    ev_t = np.array([e["t"] for e in placed])
    if ev_t.size > MAX_EVENTS:
        ev_t = np.sort(rng.choice(ev_t, MAX_EVENTS, replace=False))
    lo, hi = span[0] + SNIP_S + 1, span[1] - SNIP_S - 1
    cand = rng.uniform(lo, hi, size=max(1, ev_t.size) * NULL_PER_EVENT * 4)
    keep = []
    for t in cand:
        k = int(round((t - span[0]) * FS))
        if not ok[max(0, k - 250):k + 251].all():
            continue
        if ev_t.size and np.min(np.abs(ev_t - t)) < NULL_GAP_S:
            continue
        keep.append(t)
        if len(keep) >= ev_t.size * NULL_PER_EVENT:
            break
    nul_t = np.sort(np.array(keep))
    out["n_used"] = int(ev_t.size)
    regions = {}
    ref = None
    names = list(coupling.dewey_map())
    order = [p["region"]] + [n for n in names if n != p["region"]]
    for i, name in enumerate(order):
        say("coordination: %s (%d of %d)" % (name, i + 1, len(order)))
        ws = [c for c in wires_for(day, name) if c in files]
        if not ws:
            regions[name] = {"why": "histology rules it out" if name in (day.get("blocked") or {})
                             else "no usable wire"}
            continue
        c = wire if name == p["region"] else ws[0]
        if ev_t.size < 5:
            regions[name] = {"wire": c, "why": "too few events"}
            continue
        E = read_snippets(files[c], origin, ev_t, check=check)
        N = read_snippets(files[c], origin, nul_t, check=check)
        if name == p["region"]:
            ref = (E, N)
        got = coordination(E, N, None if name == p["region"] else ref[0],
                           None if name == p["region"] else ref[1], p, rng)
        got["wire"] = c
        regions[name] = got
    out["regions"] = regions
    out["order"] = order
    return out


def days_of(man):
    return [d for d in man["days"] if d["day"] in MO.DAY_NAMES]


def state(p, man):
    """What is done for these settings: {(rat, day): result}."""
    have = {}
    for d in days_of(man):
        got = MO._read_json(_cache_path(p, d["rat"], d["day"]))
        if got and got.get("schema") == SCHEMA:
            have[(int(d["rat"]), d["day"])] = got
    return have


def work(worker, p):
    man = MO.manifest()
    if not man:
        raise EventsError("The Monolith has no manifest yet.", 409)
    os.makedirs(cache_dir(p), exist_ok=True)
    have = state(p, man)
    todo = [d for d in days_of(man) if (int(d["rat"]), d["day"]) not in have]
    for i, d in enumerate(todo):
        worker.check()
        worker.note(phase="events", i=i, of=len(todo), item="r%d %s" % (d["rat"], d["day"]))
        got = run_day(d, p, check=worker.check,
                      say=lambda s, i=i, d=d: worker.note(item="r%d %s · %s" % (d["rat"], d["day"], s)))
        MO._write_json(_cache_path(p, d["rat"], d["day"]), got)
    return {"done": len(todo), "digest": digest(p)}


def _mean_se(rows):
    A = np.array([[np.nan if v is None else v for v in r] for r in rows], float)
    if not A.size:
        return None, None
    n = np.isfinite(A).sum(axis=0)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m = np.nanmean(A, axis=0)
        se = np.nanstd(A, axis=0, ddof=1) / np.sqrt(n)
    f = lambda v: [None if not np.isfinite(x) else round(float(x), 4) for x in v]  # noqa: E731
    return f(m), f(se)


def report(p, man):
    """Per rat-day and pooled over rats, session by session -- descriptive,
    no test. The events themselves stay in each rat-day's record."""
    have = state(p, man)
    days = []
    for d in days_of(man):
        got = have.get((int(d["rat"]), d["day"]))
        if not got:
            days.append({"rat": int(d["rat"]), "day": d["day"], "done": False})
            continue
        row = {k: got.get(k) for k in ("rat", "day", "wire", "why", "span", "usable_s",
                                       "timing", "n_used", "order")}
        row["done"] = True
        row["n_events"] = len(got.get("events") or [])
        row["events"] = [{k: e[k] for k in ("t", "z", "width_ms", "where", "rel")}
                         for e in got.get("events") or []]
        row["regions"] = {n: {k: r.get(k) for k in ("wire", "why", "n_events", "n_random", "peak",
                                                    "peak_random", "z_size", "p_size", "plv",
                                                    "plv_random", "z_plv", "p_plv", "erp", "random")}
                          for n, r in (got.get("regions") or {}).items()}
        days.append(row)
    pooled = {}
    names = list(coupling.dewey_map())
    for day in MO.DAY_NAMES:
        rows = [x for x in days if x["day"] == day and x.get("done") and not x.get("why")]
        if not rows:
            continue
        psth = [x["timing"]["psth"]["rate_per_min"] for x in rows if x["timing"]["psth"]["rate_per_min"]]
        pm, pse = _mean_se(psth)
        rate = {w: _mean_se([[x["timing"]["rate_per_min"].get(w)] for x in rows]) for w in WINDOWS + ("iti",)}
        regs = {}
        for n in names:
            rr = [x["regions"].get(n) or {} for x in rows]
            ok = [r for r in rr if r.get("erp")]
            if not ok:
                regs[n] = {"rats": 0}
                continue
            em, ese = _mean_se([r["erp"] for r in ok])
            nm, _n = _mean_se([r["random"] for r in ok])
            zs = [r["z_size"] for r in ok if r.get("z_size") is not None]
            zp = [r["z_plv"] for r in ok if r.get("z_plv") is not None]
            regs[n] = {"rats": len(ok), "erp": em, "erp_se": ese, "random": nm,
                       "z_size": round(float(np.mean(zs)), 3) if zs else None,
                       "size_rats": sum(1 for r in ok if (r.get("p_size") or 1) < 0.05),
                       "z_plv": round(float(np.mean(zp)), 3) if zp else None,
                       "plv_rats": sum(1 for r in ok if (r.get("p_plv") or 1) < 0.05),
                       "plv_of": len(zp)}
        pooled[day] = {"rats": len(rows), "events": sum(x["n_events"] for x in rows),
                       "psth": {"from": PSTH_FROM, "to": PSTH_TO, "bin": PSTH_BIN, "mean": pm, "se": pse},
                       "rate_per_min": {w: {"mean": (v[0] or [None])[0], "se": (v[1] or [None])[0]}
                                        for w, v in rate.items()},
                       "regions": regs}
    todo = sum(1 for x in days if not x["done"])
    return {"params": p, "digest": digest(p), "defaults": DEFAULTS, "regions": names,
            "days": days, "pooled": pooled, "todo": todo, "window_say": WINDOW_SAY,
            "out_fs": OUT_FS, "snip_s": SNIP_S,
            "estimate_s": int(todo * 45)}


def example(p, man, rat, day, i, half=2.0):
    """One event: every region's trace around it, from the originals."""
    d = next((x for x in days_of(man) if int(x["rat"]) == int(rat) and x["day"] == day), None)
    if not d:
        raise EventsError("r%s %s is not in the Monolith." % (rat, day), 404)
    got = MO._read_json(_cache_path(p, rat, day))
    if not got or not got.get("events"):
        raise EventsError("Find the events for these settings first.", 409)
    if not 0 <= int(i) < len(got["events"]):
        raise EventsError("There is no event %s." % (i,), 404)
    ev = got["events"][int(i)]
    folder = spc_folder(d)
    origin = nlx.recording_start_us(folder)
    files = dict(nlx.list_csc_files(folder))
    rows = []
    for name in got.get("order") or []:
        r = (got.get("regions") or {}).get(name) or {}
        c = r.get("wire")
        if c is None or c not in files:
            rows.append({"region": name, "why": r.get("why") or "no wire"})
            continue
        S = read_snippets(files[c], origin, np.array([ev["t"]]), half=half)[0]
        if not np.isfinite(S).all():
            rows.append({"region": name, "wire": c, "why": "at the rail or unreadable here"})
            continue
        b = coupling.bandpass(S, FS, p["low"], p["high"])
        rows.append({"region": name, "wire": c, "raw": _thin(S), "band": _thin(b)})
    return {"rat": int(rat), "day": day, "i": int(i), "event": ev, "half": half,
            "out_fs": OUT_FS, "rows": rows}
