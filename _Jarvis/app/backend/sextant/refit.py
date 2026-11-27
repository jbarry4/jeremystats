"""Review: you put the probe somewhere, Sextant refits around it.

Seahorse's review lets a person drag the probe on the section. When they let
go, the page sends the line (contact 1 and contact 64, CCF um) here; Sextant
searches a small neighbourhood of it -- 100 um either way in AP and ML at the
reference depth (50 um steps), 4 degrees of tilt, 80 um along the shank, the
size factor +-0.08 -- with both methods, exactly as the full placement scores, and
answers with the best pose there and how its score compares with Sextant's
own answer. A placement the recording cannot tell from the answer is said to
be as good; a worse one says which landmarks disagree most.
"""
from __future__ import annotations

import json
import math
import os
import threading

import numpy as np

from . import atlas as A
from . import detectors, evidence
from . import fit as F
from . import forward as B
from . import solve as SV

_LOCK = threading.Lock()
_CACHE = {}


def _load(logs_dir, web_dir, gid):
    with _LOCK:
        if gid in _CACHE:
            return _CACHE[gid]
    p = os.path.join(logs_dir, ".cache", "sextant", gid, "evidence.npz")
    if not os.path.exists(p):
        raise FileNotFoundError("This recording's evidence is not on this machine (it is made by "
                                "tools/sextant/run.py, on the machine with the recording).")
    ev = evidence.load(p)
    lms, _notes = detectors.detect(ev)
    bad = np.asarray(ev["is_bad"], bool) | detectors.noisy(ev)
    prof = B.profiles(ev, bad)
    with open(os.path.join(web_dir, gid + ".json"), encoding="utf-8") as f:
        rep = json.load(f)
    got = {"lms": lms, "bad": bad, "prof": prof, "answer": rep["answer"]["line"],
           "stretch": rep["answer"].get("stretch")}
    with _LOCK:
        _CACHE[gid] = got
    return got


def line_pose(line, stretch=None):
    """(ap_ref, ml_ref, tilt_ml, tilt_ap, o, s) of a 64-contact line (with a
    stretched dentate, s is CA1's size: contact 64 sits at
    pitch * s * (h + k (63 - h)) from contact 1)."""
    p1, p64 = np.asarray(line[0], float), np.asarray(line[1], float)
    v = p64 - p1
    L = float(np.linalg.norm(v))
    d = v / L
    if stretch:
        h, k = float(stretch["hinge"]), float(stretch["k"])
        s = L / (F.PITCH * (h + k * (F.NC - 1 - h)))
    else:
        s = L / ((F.NC - 1) * F.PITCH)
    t_ref = (F.DV_REF - p1[1]) / d[1]
    p_ref = p1 + t_ref * d
    return (float(p_ref[0]), float(p_ref[2]), math.degrees(math.atan2(d[2], d[1])),
            math.degrees(math.atan2(d[0], d[1])), float(-t_ref), float(s))


def _score(atl, got, ap, ml, tml, tap, offsets, scales):
    codes, t = F.lines_codes(atl, ap, ml, tml, tap)
    alm = F.atlas_landmarks(codes, t)
    st = got.get("stretch")
    ks = np.full(np.asarray(scales).size, float(st["k"])) if st else None
    h = float(st["hinge"]) if st else None
    chi = SV._chi2_a_grid(got["lms"], alm, offsets, scales, Ks=ks, hinge=h)
    _tot, parts = B.score(codes, offsets, scales, got["prof"], got["bad"], ks=ks, hinge=h)
    llb = sum(parts.values()) if parts else np.zeros_like(chi)
    return -0.5 * chi + SV.W_B * llb, chi, alm


def _line_of(ap, ml, tml, tap, o, s, stretch=None):
    d = A.direction(tml, tap)
    p_ref = np.array([ap, F.DV_REF, ml])
    c1 = p_ref + o * d
    if stretch:
        c64 = c1 + float(F.t_of_x(F.NC - 1, s, float(stretch["hinge"]), float(stretch["k"]))) * d
    else:
        c64 = c1 + (F.NC - 1) * F.PITCH * s * d
    return [[round(float(x), 1) for x in c1], [round(float(x), 1) for x in c64]]


def local(logs_dir, web_dir, gid, line):
    atl = A.load()
    got = _load(logs_dir, web_dir, gid)
    ap0, ml0, tm0, ta0, o0, s0 = line_pose(line, got.get("stretch"))
    # 50 um and 4 degrees: a review is a drag and a look, and another drag
    # refines it; the full search's grid would keep the person waiting
    dd = np.arange(-100.0, 100.1, 50.0)
    dt = np.arange(-4.0, 4.1, 4.0)
    G = np.stack(np.meshgrid(ap0 + dd, ml0 + dd, tm0 + dt, ta0 + dt, indexing="ij"), -1).reshape(-1, 4)
    offsets = o0 + np.arange(-80.0, 80.1, 20.0)
    scales = np.clip(s0 + np.array([-0.08, 0.0, 0.08]), *F.SCALE_RANGE)
    tot = np.full((G.shape[0], offsets.size, scales.size), -np.inf, np.float32)
    chi = np.zeros_like(tot)
    for i in range(0, G.shape[0], 150):
        sl = slice(i, i + 150)
        T, C, _alm = _score(atl, got, G[sl, 0], G[sl, 1], G[sl, 2], G[sl, 3], offsets, scales)
        tot[sl], chi[sl] = T, C
    li, oi, si = np.unravel_index(int(np.argmax(tot)), tot.shape)
    best = _line_of(G[li, 0], G[li, 1], G[li, 2], G[li, 3], offsets[oi], scales[si], got.get("stretch"))
    # the answer, scored the same way (its own pose, nothing searched)
    a = line_pose(got["answer"], got.get("stretch"))
    Ta, _Ca, _ = _score(atl, got, np.array([a[0]]), np.array([a[1]]), np.array([a[2]]), np.array([a[3]]),
                        np.array([a[4]]), np.array([a[5]]))
    best_score = float(tot[li, oi, si])
    ans_score = float(Ta[0, 0, 0])
    moved = float(max(np.linalg.norm(np.asarray(best[k]) - np.asarray(line[k], float)) for k in (0, 1)))
    # which landmarks disagree most at the refitted pose
    codes, t = F.lines_codes(atl, G[li:li + 1, 0], G[li:li + 1, 1], G[li:li + 1, 2], G[li:li + 1, 3])
    alm = F.atlas_landmarks(codes, t)
    worst = []
    o, s = offsets[oi], scales[si]
    for l in got["lms"]:
        if l["key"] not in F.MATCH or not l.get("fit", True) or l.get("side"):
            continue
        Lk = alm[F.MATCH[l["key"]][0]][0]
        if not np.isfinite(Lk):
            worst.append((99.0, l["key"]))
            continue
        st = got.get("stretch")
        x = float(F.x_of_t(Lk - o, s, float(st["hinge"]), float(st["k"]))) if st else (Lk - o) / (F.PITCH * s)
        worst.append((abs(x - l["x"]) / l["sigma"], l["key"]))
    worst.sort(reverse=True)
    words = {"sp": "CA1's cell layer", "spw_rev": "the sharp wave's reversal", "sr_sink": "radiatum",
             "slm_src": "lacunosum-moleculare", "fissure": "the fissure", "ml_a": "the upper molecular layer",
             "ml_b": "the lower molecular layer", "dg_core": "the granule cells", "dg_end": "the dentate's edge",
             "th_top": "the thalamus"}
    bad_ones = [words.get(k, k) for z, k in worst[:2] if z > 2.0]
    return {"ok": True, "line": best, "moved_um": round(moved, 1), "score": round(best_score, 2),
            "answer_score": round(ans_score, 2), "delta": round(best_score - ans_score, 2),
            "worst": " and ".join(bad_ones) if bad_ones else None}
