"""A placement, written down: what Seahorse's Sextant reads.

One JSON per recording (web/seahorse/sextant/<gid>.json): the evidence curves
down the shank, the landmarks with their reasons, the reveal's stops (each
with its cloud of probes), the answer with its ranges and confidence words,
each method alone, the drop-one-signal results, and the layer under every
contact as StrataScope names it (the proposal).

Coordinates are CCF micrometres (AP, DV, ML) on the RIGHT hemisphere, where
the layer atlas is; `side` says where the probe really was (the lab's feeder
sheet), and the page says so when it draws a left probe on the right.
"""
from __future__ import annotations

import numpy as np

from . import atlas as A
from . import evidence as E
from . import fit as F

# atlas layer -> StrataScope region id (backend/layers.py REGIONS); CA2/CA3
# have no StrataScope name, so a contact there gets no proposal
TO_STRATA = {
    "ca1so": "ca1_so", "ca1sp": "ca1_sp", "ca1sr": "ca1_rad", "ca1slm": "ca1_slm",
    "oml1": "dg_oml1", "mml1": "dg_mml1", "iml1": "dg_iml1", "gcl1": "dg_gcl1",
    "hil": "hil", "gcl2": "dg_gcl2", "iml2": "dg_iml2", "mml2": "dg_mml2", "oml2": "dg_oml2",
    "alv": "out", "wm": "out", "fi": "out", "ctx": "out", "vent": "out", "out": "out",
    "th": "thal",
}
# How narrow a 95% range must be to be called sure / likely (wider: a guess).
CONF = {"ap": (0.15, 0.35), "ml": (0.15, 0.35), "depth": (60.0, 150.0), "tilt": (4.0, 9.0)}


def _r(x, d=1):
    return [round(float(v), d) for v in x]


def _line(pose):
    pts = F.pose_points(pose)
    return [_r(pts[0]), _r(pts[-1])]


def _word(half, key):
    a, b = CONF[key]
    return "sure" if half <= a else ("likely" if half <= b else "guess")


def _curve(v, dp=3):
    v = np.asarray(v, float)
    return [None if not np.isfinite(x) else round(float(x), dp) for x in v]


def _norm(v, bad):
    v = np.where(bad, np.nan, np.asarray(v, float))
    lo, hi = np.nanmin(v), np.nanmax(v)
    return (v - lo) / (hi - lo) if hi > lo else v * 0


def _signed(v, bad):
    v = np.where(bad, np.nan, np.asarray(v, float))
    m = np.nanmax(np.abs(v))
    return v / m if m > 0 else v


def curves(ev, bad):
    out = {}
    with np.errstate(all="ignore"):
        out["mua"] = _norm(ev["c_mua"], bad)
        out["ripple_theta"] = _norm(np.log(ev["c_ripple"] / ev["c_theta_still"]), bad)
        out["theta"] = _norm(np.abs(ev["theta_cx"]), bad)
        ph = np.degrees(np.unwrap(np.nan_to_num(np.angle(ev["theta_cx"]))))
        out["theta_phase"] = np.where(bad, np.nan, ph - np.nanmin(np.where(bad, np.nan, ph)))
        for g in ("slow_gamma", "mid_gamma", "fast_gamma"):
            out[g] = _norm(ev["c_" + g], bad)
    if "rip_power" in ev:
        out["ripple_events"] = _norm(ev["rip_power"], bad)
    if "spw" in ev:
        out["spw"] = _signed(ev["spw"], bad)
        out["spw_csd"] = _signed(E.csd(ev["spw"], bad), bad)
    for k in ("ds", "ps", "bt"):
        if k + "_peak" in ev and ev.get("n_" + k, 0) >= 5:
            out[k] = _signed(ev[k + "_peak"], bad)
            out[k + "_csd"] = _signed(E.csd(ev[k + "_peak"], bad), bad)
    return {k: _curve(v) for k, v in out.items()}


def build(atl, rec, ev, lms, notes, out, bad):
    side = rec.get("hemisphere")
    best = out["consolidated"]["pose"]
    d = F.describe(atl, best, side)
    eps = [F.describe(atl, p, side) for p in out["samples"]]

    def rng(vals):
        v = np.asarray(vals, float)
        lo, mid, hi = np.percentile(v, [2.5, 50, 97.5])
        return {"lo": round(float(lo), 3), "mid": round(float(mid), 3), "hi": round(float(hi), 3),
                "half": round(float(hi - lo) / 2.0, 3)}
    ranges = {
        "entry_ap": rng([e["entry"]["ap"] for e in eps]),
        "entry_ml": rng([abs(e["entry"]["ml"]) for e in eps]),
        "depth1": rng([e["depth_um"]["contact1"] for e in eps]),
        "depth64": rng([e["depth_um"]["contact64"] for e in eps]),
        "tilt_ml": rng([e["tilt_ml"] for e in eps]),
        "tilt_ap": rng([e["tilt_ap"] for e in eps]),
        "scale": rng([e["scale"] for e in eps]),
        "k": rng([e.get("k", 1.0) for e in eps]),
    }
    words = {"ap": _word(ranges["entry_ap"]["half"], "ap"),
             "ml": _word(ranges["entry_ml"]["half"], "ml"),
             "depth": _word(ranges["depth1"]["half"], "depth"),
             "tilt": _word(max(ranges["tilt_ml"]["half"], ranges["tilt_ap"]["half"]), "tilt")}
    # drop one signal: how far the answer moves without it
    c0 = np.asarray(_line(best))
    drops = []
    for dr in out["drops"]:
        c1 = np.asarray(_line(dr["pose"]))
        move = float(np.max(np.linalg.norm(c1 - c0, axis=1)))
        drops.append({"kind": dr["kind"], "key": dr["key"], "move_um": round(move),
                      "line": c1.tolist()})
    cloud_spread = float(np.median([np.max(np.linalg.norm(np.asarray(_line(p)) - c0, axis=1))
                                    for p in out["samples"]]))
    for dr in drops:
        dr["fragile"] = bool(dr["move_um"] > max(2.0 * cloud_spread, 150.0))
    stops = []
    for st in out["stops"]:
        stops.append({"id": st["id"], "title": st["title"], "landmarks": st["landmarks"],
                      "profiles": st["profiles"], "best": _line(st["best"]),
                      "k": round(float(st["best"].get("k") or 1.0), 3),
                      "cloud": [_line(p) for p in st["cloud"][:60]]})
    layers = d["layers"]
    return {
        "schema": 1, "gid": rec["gid"], "mouse": rec["mouse"], "group": rec["group"],
        "side": side, "ko": rec.get("ko"), "pspikes": rec.get("pspikes"),
        "label": rec.get("label"),
        "probe": {"name": "H3", "n": 64, "pitch_um": 20.0},
        "bad": [int(k) + 1 for k in np.flatnonzero(bad)],
        "evidence": {"curves": curves(ev, bad),
                     "counts": {k: int(ev.get("n_" + k, 0)) for k in ("ripples", "troughs", "ds", "ps", "bt")},
                     "walk_s": round(float(ev.get("walk_s", 0))), "still_s": round(float(ev.get("still_s", 0))),
                     "states": ev.get("states_how")},
        "landmarks": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in l.items()
                       if k in ("key", "x", "sigma", "why", "source", "side", "fit")} for l in lms],
        "notes": notes,
        "answer": {
            "line": _line(best), "entry": d["entry"], "contact1": d["contact1"], "contact64": d["contact64"],
            "depth_um": d["depth_um"], "tilt_ml": d["tilt_ml"], "tilt_ap": d["tilt_ap"], "scale": d["scale"],
            "layers": layers, "strata": [TO_STRATA.get(k) for k in layers],
            "stretch": ({"k": round(float(best.get("k") or 1.0), 3), "hinge": round(float(out["hinge"]), 2)}
                        if out.get("hinge") is not None else None),
            "ranges": ranges, "words": words,
        },
        "methods": {k: {"line": _line(out[k]["pose"]), "chi2_a": round(out[k]["chi2_a"], 2),
                        "ll_b": round(out[k]["ll_b"], 1),
                        "entry": F.describe(atl, out[k]["pose"], side)["entry"]}
                    for k in ("A", "B", "consolidated")},
        "stops": stops,
        "drops": drops,
        "cloud": [_line(p) for p in out["samples"][:80]],
    }
