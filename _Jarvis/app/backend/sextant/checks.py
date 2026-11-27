"""Find a planted probe: how well can Sextant find a probe it did not see?

A probe is planted at a known pose near the craniotomy. Its evidence is made
from the atlas: every landmark the line crosses, at the contact it falls on,
moved by that detector's own scatter (its sigma); and the current profiles
(dentate spikes, the sharp wave, theta) from the pathways laid on the line's
layers, plus noise. Then the full search runs on that evidence, blind, and
the answer is compared with the plant.

What this measures, and what it does not. It is the inference's own
precision -- how far the answer strays when the evidence is as noisy as the
detectors say -- and whether the cloud's 95% ranges hold the plant 95% of the
time. It assumes the atlas and the pathway model are right; a real brain
that differs from the atlas adds error this cannot see. So it is the best
Sextant can do, and the ranges it validates are a floor.
"""
from __future__ import annotations

import numpy as np

from . import atlas as A
from . import fit as F
from . import forward as B
from . import solve as SV

SIGMA = {"sp": 1.0, "sr_sink": 2.5, "slm_src": 2.5, "fissure": 3.0, "ml_a": 1.5, "ml_b": 1.5,
         "dg_end": 2.5, "th_top": 3.0}
KEY_OF = {"sp": "sp_c", "sr_sink": "sr_c", "slm_src": "slm_c", "fissure": "fis", "ml_a": "mla",
          "ml_b": "mlb", "dg_end": "dge", "th_top": "tht"}
GAINS = {"ds": {"lpp1": 0.35, "mpp1": 1.0, "lpp2": 0.3, "mpp2": 0.8, "ec_ca1": 0.15},
         "spw": {"sc_ca1": 1.0, "ec_ca1": -0.35, "dg_all": 0.3},
         "theta": {"ec_ca1": 1.0, "sc_ca1": 0.45j, "dg_all": 0.7 - 0.2j}}


def plant(atl, rng):
    """A random true pose whose shank spans the hippocampus: (pose dict,
    the line's codes)."""
    c = A.from_bregma(-2.2, 1.4)
    for _try in range(400):
        ap = c[0] + rng.normal(0, 350)
        ml = c[2] + rng.normal(0, 300)
        tml, tap = rng.uniform(-8, 8), rng.uniform(-8, 8)
        s = rng.uniform(0.9, 1.1)
        codes, t = F.lines_codes(atl, np.array([ap]), np.array([ml]), np.array([tml]), np.array([tap]))
        alm = F.atlas_landmarks(codes, t)
        if not (np.isfinite(alm["sp_c"][0]) and np.isfinite(alm["mla"][0])):
            continue
        # contact 1 a little above or below CA1's cell layer
        x_sp = rng.uniform(-4, 10)
        o = float(alm["sp_c"][0]) - F.PITCH * s * x_sp
        x_mla = (alm["mla"][0] - o) / (F.PITCH * s)
        if not (5 < x_mla < 55):
            continue
        return {"ap": ap, "ml": ml, "tml": tml, "tap": tap, "o": o, "s": s}, codes, t, alm
    raise RuntimeError("no plantable pose found")


def evidence_of(true, codes, t, alm, rng, noise=0.2):
    """Landmarks and profiles for a planted probe."""
    lms = []
    for key, ak in KEY_OF.items():
        L = alm[ak][0]
        if not np.isfinite(L):
            continue
        x = (L - true["o"]) / (F.PITCH * true["s"])
        if key == "sp" and x < 1:
            lms.append({"key": "sp_above", "x": 0.5, "sigma": 1.5, "side": "above"})
            continue
        if not (0.5 < x < F.NC - 1.5):
            continue
        sig = SIGMA[key]
        lms.append({"key": key, "x": float(x + rng.normal(0, sig)), "sigma": sig})
    # profiles from the pathways on the true line
    V, ind = B.bases(codes)
    tc = true["o"] + F.PITCH * true["s"] * np.arange(F.NC)
    def samp(a):
        f = (tc - F.T0) / F.DT
        i0 = np.clip(np.floor(f).astype(int), 0, a.shape[1] - 2)
        w = f - i0
        return a[0, i0] * (1 - w) + a[0, i0 + 1] * w
    ev = {"is_bad": np.zeros(F.NC, bool), "n_ds": 200, "n_ripples": 200}
    for name, key in (("ds", "ds_peak"), ("spw", "spw"), ("theta", "theta_cx")):
        y = sum(g * samp(V[p]) for p, g in GAINS[name].items())
        y = np.asarray(y)
        sd = np.sqrt(np.mean(np.abs(y) ** 2))
        n = rng.normal(0, noise * sd, F.NC) + (1j * rng.normal(0, noise * sd, F.NC) if np.iscomplexobj(y) else 0)
        ev[key] = y + n
    sp = samp(B._movavg(ind["sp"]))
    gc = samp(B._movavg(ind["gcl1"] + ind["gcl2"] + ind["hil"]))
    below = samp(B._movavg(ind["below"]))
    ev["c_mua"] = np.exp(np.log(12.0) + 0.45 * sp + 0.25 * gc + 0.5 * below + rng.normal(0, 0.03, F.NC))
    ev["rip_power"] = 1.0 + 1.4 * sp + rng.normal(0, 0.06, F.NC)
    return lms, ev


def run_one(atl, rng, log=print):
    true, codes, t, alm = plant(atl, rng)
    lms, ev = evidence_of(true, codes, t, alm, rng)
    bad = ev["is_bad"]
    out = SV.place(atl, ev, lms, bad, log=lambda *a: None, rng=rng)
    tp = {"centre": None}
    d_true = A.direction(true["tml"], true["tap"])
    c1 = np.array([true["ap"], F.DV_REF, true["ml"]]) + true["o"] * d_true
    tpose = {"centre": c1 + (F.NC - 1) / 2.0 * F.PITCH * true["s"] * d_true, "dir": d_true,
             "scale": true["s"], "tilt_ml": true["tml"], "tilt_ap": true["tap"]}
    T = F.describe(atl, tpose)
    G = F.describe(atl, out["consolidated"]["pose"])
    E = [F.describe(atl, p) for p in out["samples"]]

    def inside(key, f):
        v = np.array([f(e) for e in E])
        lo, hi = np.percentile(v, [2.5, 97.5])
        return bool(lo <= f(T) <= hi), float(f(G) - f(T))
    res = {}
    for name, f in (("ap", lambda e: e["entry"]["ap"]), ("ml", lambda e: abs(e["entry"]["ml"])),
                    ("depth", lambda e: e["depth_um"]["contact1"] / 1000.0),
                    ("tilt_ml", lambda e: e["tilt_ml"]), ("tilt_ap", lambda e: e["tilt_ap"])):
        ok, err = inside(name, f)
        res[name] = {"err": round(err, 3), "covered": ok}
    log("   planted AP %.2f ML %.2f -> AP %.2f ML %.2f | errors AP %+.2f ML %+.2f mm, depth %+.0f um, tilts %+.1f/%+.1f" % (
        T["entry"]["ap"], abs(T["entry"]["ml"]), G["entry"]["ap"], abs(G["entry"]["ml"]),
        res["ap"]["err"], res["ml"]["err"], 1000 * res["depth"]["err"], res["tilt_ml"]["err"], res["tilt_ap"]["err"]))
    return res
