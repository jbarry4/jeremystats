"""Evidence -> landmarks: where along the shank each known layer is.

Each detector reads one kind of evidence and says "this landmark is at
contact x (0-based, sub-contact), give or take sigma contacts", or nothing.
Every one is tied to a published laminar profile; the citation travels with
the landmark so the reveal can say why.

    sp        CA1 pyramidal layer   ripple/theta power (still) peak,
                                    multiunit peak, ripple-band power during
                                    ripples (Buzsaki 2015; Toothy's rule)
    spw_rev   sp / sr border        the sharp wave's polarity reversal
                                    (Ylinen et al. 1995)
    sr_sink   middle of radiatum    the sharp wave's current sink (Schaffer
                                    collaterals; Ylinen 1995, Buzsaki 2015)
    slm_src   lacunosum-moleculare  the sharp wave's return source
                                    (Castelli et al. 2025)
    fissure   hippocampal fissure   theta amplitude's first maximum below the
                                    cell layer (Winson 1974; Buzsaki 2002)
    ml_a      upper molecular layer dentate spikes' first current sink
                                    (Bragin et al. 1995; Dvorak et al. 2021)
    dg_core   granule / hilar core  dentate spikes' source between the sinks
    ml_b      lower molecular layer dentate spikes' second sink
    dg_end    bottom of the dentate where the lower sink's current ends
    hil_gam   dentate core          mid/fast gamma maximum in the dentate
                                    (Bragin et al. 1995)
    th_top    top of the thalamus   multiunit activity rising again below
                                    the hippocampus
    ps_a/ps_b P-spike sinks         (PTEN) layered like dentate spikes but
    bt_a/bt_b BT sinks              wider (Boublil & Ewell 2024 abstract)

A detector that cannot find its landmark says so (and why), rather than
guessing: a missing landmark costs the fit nothing, a wrong one costs a lot.
"""
from __future__ import annotations

import numpy as np

from . import evidence as E

N = E.N


def _nan(v, bad):
    v = np.array(v, float, copy=True)
    v[bad] = np.nan
    return v


def _smooth(v, w=1):
    if w <= 0:
        return v
    k = np.ones(2 * w + 1)
    x = np.where(np.isfinite(v), v, 0.0)
    m = np.isfinite(v).astype(float)
    num = np.convolve(x, k, "same")
    den = np.convolve(m, k, "same")
    with np.errstate(invalid="ignore"):
        out = num / den
    out[den == 0] = np.nan
    return out


def _parabolic(v, k):
    """Sub-contact position of an extremum at k."""
    if k <= 0 or k >= v.size - 1 or not np.all(np.isfinite(v[k - 1:k + 2])):
        return float(k)
    a, b, c = v[k - 1], v[k], v[k + 1]
    d = a - 2 * b + c
    if d == 0:
        return float(k)
    return float(k + 0.5 * (a - c) / d)


def _centroid(v, k, frac=0.5):
    """Centroid of the lobe around k of a positive-going v (above frac of
    its height)."""
    h = v[k] * frac
    lo = k
    while lo - 1 >= 0 and np.isfinite(v[lo - 1]) and v[lo - 1] > h:
        lo -= 1
    hi = k
    while hi + 1 < v.size and np.isfinite(v[hi + 1]) and v[hi + 1] > h:
        hi += 1
    w = np.clip(v[lo:hi + 1] - h, 0, None)
    if w.sum() <= 0:
        return float(k), lo, hi
    return float((w * np.arange(lo, hi + 1)).sum() / w.sum()), lo, hi


def _lm(key, x, sigma, why, source, **kw):
    d = {"key": key, "x": float(x), "sigma": float(sigma), "why": why, "source": source}
    d.update(kw)
    return d


GAIN_KEYS = ("c_delta_still", "c_theta_still", "c_slow_gamma", "c_mid_gamma")
JUMP_KEYS = ("c_rms", "c_delta_still", "c_theta_still")


def _dev(ev, key, base):
    """Log power at each contact against what its neighbours on BOTH sides
    predict (straight lines through the pairs k-1/k+1 and k-2/k+2), so a
    steady gradient -- theta falling off below the dentate -- is not a
    deviation. A contact without a good neighbour on each side is not
    judged (NaN)."""
    with np.errstate(all="ignore"):
        v = np.log(np.where(base, np.nan, np.asarray(ev[key], float)))
    d = np.full(N, np.nan)
    for k in range(N):
        if not np.isfinite(v[k]):
            continue
        up = [v[j] for j in (k - 2, k - 1) if j >= 0 and np.isfinite(v[j])]
        dn = [v[j] for j in (k + 1, k + 2) if j < N and np.isfinite(v[j])]
        if up and dn:
            d[k] = v[k] - float(np.median(up + dn))
    return d


def noisy(ev):
    """Contacts whose own recording chain differs from their neighbours'.

    Two signatures, both measured as log power against the median of the two
    contacts either side:
      gain   delta, theta, slow and mid gamma all shifted the same way by more
             than 10% (median of the four) -- m22's contact 25 sat 15-20%
             low in all four while its multiunit and ripple power rose;
      jump   broadband, delta or theta power more than 35% off -- m22's
             contact 9 (delta more than double its neighbours').
    A cell layer does neither: it lifts multiunit and ripple power, and the
    theta minimum at CA1's phase reversal is theta alone (m59's contact 6),
    with gamma untouched. Returns a mask."""
    base = np.asarray(ev["is_bad"], bool)
    G = np.stack([_dev(ev, k, base) for k in GAIN_KEYS])
    with np.errstate(all="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        med = np.nanmedian(G, axis=0)
    same = np.all(np.sign(G) == np.sign(med)[None, :], axis=0) & np.all(np.abs(np.nan_to_num(G)) > 0.05, axis=0)
    gain = np.isfinite(med) & (np.abs(med) > 0.10) & same
    J = np.stack([_dev(ev, k, base) for k in JUMP_KEYS])
    jump = np.nanmax(np.abs(np.nan_to_num(J)), axis=0) > np.log(1.35)
    return (gain | jump) & ~base


def detect(ev):
    """All landmarks found in one recording's evidence, and the notes of the
    ones not found. Returns (landmarks, notes)."""
    extra = noisy(ev)
    ev = dict(ev)
    ev["is_bad"] = np.asarray(ev["is_bad"], bool) | extra
    bad = ev["is_bad"]
    lms, notes = [], []
    if extra.any():
        notes.append("Left out as noisy (they break from both neighbours on two measures): contact %s."
                     % ", ".join(str(k + 1) for k in np.flatnonzero(extra)))

    # ---- CA1 pyramidal layer --------------------------------------------
    sp = E.sp_contact(ev)
    if sp is not None and sp <= 1:
        notes.append("Ripples are strongest at the top contact: CA1's cell layer is at or above the probe's top.")
        lms.append(_lm("sp_above", 0.5, 1.5,
                       "ripples only grow toward the top: CA1's cell layer is above the first contact",
                       "Buzsaki 2015", side="above"))
        sp = None
    elif sp is None:
        notes.append("No ripple/theta peak above the theta maximum: no CA1 cell layer on this probe.")
    else:
        with np.errstate(all="ignore"):
            r = np.log(ev["c_ripple"] / ev["c_theta_still"])
        r = _nan(r, bad)
        votes = [(_parabolic(r, sp), 1.0, "ripple / theta (still)")]
        mua = _nan(ev["c_mua"], bad)
        lo, hi = max(0, sp - 4), min(N, sp + 5)
        km = lo + int(np.nanargmax(mua[lo:hi]))
        if E._local_max(mua, km, 2) and lo < km < hi - 1:
            votes.append((_parabolic(mua, km), 1.6, "multiunit peak"))
        if "rip_power" in ev:
            rp = _nan(ev["rip_power"], bad)
            kr = lo + int(np.nanargmax(rp[lo:hi]))
            if E._local_max(rp, kr, 2):
                votes.append((_parabolic(rp, kr), 1.2, "ripple-band power during ripples"))
        xs = np.array([v[0] for v in votes])
        ws = 1.0 / np.array([v[1] for v in votes]) ** 2
        x = float((xs * ws).sum() / ws.sum())
        spread = float(np.sqrt(((xs - x) ** 2 * ws).sum() / ws.sum())) if xs.size > 1 else 0.0
        lms.append(_lm("sp", x, max(1.0, spread, 1.0 / np.sqrt(ws.sum())),
                       "CA1's cell layer: where ripples are strongest against theta and units fire most",
                       "Buzsaki 2015; Toothy ripple rule", votes=[[float(a), b, c] for a, b, c in votes]))

    # ---- the sharp wave -------------------------------------------------
    if sp is not None and "spw" in ev and ev.get("n_ripples", 0) >= 20:
        spw = _nan(ev["spw"], bad)
        # polarity reversal below the cell layer: the zero crossing from the
        # sign at sp to the opposite sign of the radiatum trough
        k0 = int(round(lms[0]["x"]))
        seg = spw[k0:min(N, k0 + 15)]
        if np.isfinite(seg).sum() > 5:
            j_ext = int(np.nanargmax(np.abs(seg)))
            s_ext = np.sign(seg[j_ext])
            cross = None
            for j in range(0, j_ext):
                a, b = seg[j], seg[j + 1]
                if np.isfinite(a) and np.isfinite(b) and np.sign(a) == -s_ext and np.sign(b) == s_ext:
                    cross = k0 + j + a / (a - b)
            if cross is None and np.isfinite(spw[max(0, k0 - 3):k0]).any():
                up = spw[max(0, k0 - 6):k0 + 1]
                for j in range(up.size - 1):
                    a, b = up[j], up[j + 1]
                    if np.isfinite(a) and np.isfinite(b) and np.sign(a) != np.sign(b):
                        cross = max(0, k0 - 6) + j + a / (a - b)
            if cross is not None:
                lms.append(_lm("spw_rev", cross, 1.5,
                               "the sharp wave flips sign where the cell layer meets stratum radiatum",
                               "Ylinen et al. 1995"))
        c = E.csd(spw, bad)
        c = _smooth(c, 1)
        # radiatum sink: the deepest sink 3-20 contacts below the cell layer
        # (never at the cell layer's own edge, where the CSD is the cell
        # layer's source turning over)
        lo, hi = k0 + 3, min(N - 1, k0 + 21)
        if hi - lo > 4 and np.isfinite(c[lo:hi]).any():
            ks = lo + int(np.nanargmin(c[lo:hi]))
            if c[ks] < 0 and lo < ks < hi - 1:
                cx, a, b = _centroid(-c, ks, 0.4)
                lms.append(_lm("sr_sink", cx, 2.5,
                               "the sharp wave's sink: CA3's Schaffer collaterals landing in stratum radiatum",
                               "Ylinen et al. 1995; Buzsaki 2015"))
                # return source below it, before the dentate
                lo2, hi2 = b + 2, min(N - 1, b + 16)
                if hi2 - lo2 > 2 and np.isfinite(c[lo2:hi2]).any():
                    kq = lo2 + int(np.nanargmax(c[lo2:hi2]))
                    if c[kq] > 0.25 * abs(c[ks]) and lo2 < kq < hi2 - 1:
                        qx, _a, _b = _centroid(c, kq, 0.4)
                        lms.append(_lm("slm_src", qx, 2.5,
                                       "the sharp wave's return current: stratum lacunosum-moleculare",
                                       "Castelli et al. 2025"))

    # ---- the fissure: theta's first maximum below the cell layer ---------
    th = _smooth(_nan(np.abs(ev["theta_cx"]), bad), 1)
    thw = _smooth(_nan(ev["c_theta"], bad), 1)
    fis = None
    k0 = int(round(lms[0]["x"])) if lms and lms[0]["key"] == "sp" else 0
    for prof, name in ((thw, "walking theta power"), (th, "the theta wave's amplitude")):
        for k in range(k0 + 3, N - 2):
            if E._local_max(prof, k, 3) and prof[k] > np.nanmedian(prof):
                if fis is None:
                    fis = (k, name, prof)
                break
    if fis is not None:
        k, name, prof = fis
        lms.append(_lm("fissure", _parabolic(prof, k), 3.0,
                       "theta is largest at the hippocampal fissure",
                       "Winson 1974; Buzsaki 2002"))
    else:
        notes.append("No theta maximum below the cell layer.")

    # ---- dentate events: DS, then P-spikes and BTs ------------------------
    floor = (int(round(lms[0]["x"])) + 8) if (lms and lms[0]["key"] == "sp") else 4
    for kind, tag, sig in (("ds", "", 1.5), ("ps", "ps_", 2.0), ("bt", "bt_", 2.5)):
        if kind + "_peak" not in ev or ev.get("n_" + kind, 0) < (20 if kind == "ds" else 8):
            continue
        got = _dentate_pattern(ev[kind + "_peak"], bad, floor)
        name = {"ds": "dentate spikes", "ps": "P-spikes", "bt": "borderline transients"}[kind]
        if not got:
            notes.append("The %s' current has no clear sink in the dentate." % name)
            continue
        a, core, b, end = got
        lms.append(_lm(tag + "ml_a" if tag else "ml_a", a, sig,
                       "%s' upper sink: the perforant path landing in the molecular layer" % name,
                       "Bragin et al. 1995; Dvorak et al. 2021"))
        if b is not None:
            lms.append(_lm(tag + "ml_b" if tag else "ml_b", b, sig,
                           "%s' lower sink: the other blade's molecular layer" % name,
                           "Bragin et al. 1995; Senzai & Buzsaki 2017"))
        elif core is not None:
            # one blade only: its return current (granule cells) is the second
            # fix; with two sinks the core adds nothing they do not say
            lms.append(_lm(tag + "dg_core" if tag else "dg_core", core, sig + 1.5,
                           "%s' return current: the granule cells under the one blade crossed" % name,
                           "Bragin et al. 1995"))
        if end is not None and kind == "ds":
            lms.append(_lm("dg_end", end, 2.5,
                           "where the dentate spike's current ends: the bottom of the dentate",
                           "Bragin et al. 1995"))

    # ---- dentate gamma (shown, not fitted: its peak sits between the middle
    # molecular layer -- fast gamma from MEC, Fernandez-Ruiz 2021 -- and the
    # hilus -- Bragin 1995 -- and which wins differs by mouse) -------------
    mg = _smooth(_nan(ev["c_fast_gamma"], bad), 1)
    if fis is not None:
        lo, hi = fis[0], min(N, fis[0] + 20)
        if np.isfinite(mg[lo:hi]).any():
            kg = lo + int(np.nanargmax(mg[lo:hi]))
            if lo < kg < hi - 1:
                lms.append(_lm("hil_gam", _parabolic(mg, kg), 3.0,
                               "fast gamma is strongest in the dentate (shown; not used in the fit)",
                               "Bragin et al. 1995; Fernandez-Ruiz et al. 2021", fit=False))

    # ---- below the hippocampus: multiunit activity rises in the thalamus ----
    mua = _smooth(_nan(ev["c_mua"], bad), 1)
    start = None
    for key in ("dg_end", "ml_b", "dg_core", "ml_a"):
        hit = [l for l in lms if l["key"] == key]
        if hit:
            start = int(round(hit[0]["x"]))
            break
    if start is not None and start < N - 8:
        seg = mua[start:]
        if np.isfinite(seg).sum() > 6:
            kmin = start + int(np.nanargmin(seg[: max(4, seg.size - 4)]))
            tail = mua[kmin:]
            rise = np.nanmax(tail) - mua[kmin]
            if rise > 0.2 * np.nanmax(mua) and kmin < N - 4:
                half = mua[kmin] + 0.5 * rise
                kk = kmin + int(np.argmax(np.nan_to_num(tail, nan=-1) >= half))
                lms.append(_lm("th_top", kk, 3.0,
                               "multiunit activity climbs again below the hippocampus: the thalamus",
                               "Allen CCFv3 (thalamus under dorsal hippocampus)"))
    return lms, notes


def _dentate_pattern(peak, bad, floor):
    """(upper sink, core source, lower sink, end) of a dentate event's CSD at
    its peak, as sub-contact positions (None where absent).

    The two blades are the two LARGEST sinks below `floor` (8 contacts under
    CA1's cell layer), at least 5 contacts apart with a source between them
    and the second at least 35% of the first -- not the first two in order:
    dentate spikes also carry smaller sinks in CA1's lacunosum-moleculare
    (seen in m59), which would otherwise be taken for a blade."""
    c = _smooth(E.csd(peak, bad), 1)
    if not np.isfinite(c).any():
        return None
    lo = max(1, int(floor))
    seg = c[lo:]
    if not np.isfinite(seg).any():
        return None
    depth = np.nanmax(np.abs(seg))
    if not np.isfinite(depth) or depth <= 0:
        return None
    mins = [k for k in range(lo, N - 1)
            if np.isfinite(c[k]) and c[k] < -0.2 * depth and c[k] <= np.nanmin(c[max(lo, k - 3):k + 4])]
    if not mins:
        return None
    mins.sort(key=lambda k: c[k])                     # deepest first
    s1 = mins[0]
    s2 = None
    for k in mins[1:]:
        if abs(k - s1) < 5 or c[k] > 0.35 * c[s1]:
            continue
        a_, b_ = sorted((s1, k))
        if np.nanmax(c[a_:b_ + 1]) > 0:
            s2 = k
            break
    a = min(s1, s2) if s2 is not None else s1
    b = max(s1, s2) if s2 is not None else None
    ax, _l, a_hi = _centroid(-c, a, 0.4)
    core = None
    if b is not None:
        bx, b_lo, b_hi = _centroid(-c, b, 0.4)
        kq = a + int(np.nanargmax(c[a:b + 1]))
        if c[kq] > 0:
            core, _l2, _h2 = _centroid(c, kq, 0.4)
    else:
        bx, b_hi = None, a_hi
        seg = c[a_hi:min(N, a_hi + 10)]
        if np.isfinite(seg).any():
            kq = a_hi + int(np.nanargmax(seg))
            if c[kq] > 0:
                core, _l2, _h2 = _centroid(c, kq, 0.4)
    # where the last sink's current has ended: back within 10% of the peak,
    # past the source that follows it
    end = None
    last_hi = b_hi if b is not None else a_hi
    seen_src = False
    for k in range(last_hi, N - 1):
        if not np.isfinite(c[k]):
            continue
        if c[k] > 0.1 * depth:
            seen_src = True
        if seen_src and abs(c[k]) < 0.1 * depth:
            end = float(k)
            break
    return ax, core, bx, end
