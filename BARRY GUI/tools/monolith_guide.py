# -*- coding: utf-8 -*-
"""The Monolith Guide's synthetic examples, made by the real engine.

    python tools\\monolith_guide.py        -> web/monolith_guide.json

Every number the page's ? popovers and the Guide page show for "a strong
effect" and "no effect" is computed here by the same code the Monolith ran
-- `sweep.explain` (which takes its numbers from `sweep.window_measures`)
for the measures, and `monolith.day_stats` / `layer_changes` / `pool` for
the statistics -- on signals made to be like the real ones: 10 s windows at
1000 Hz, 8 rats, 15 cue pairs a day. Seeded, so the file is the same every
time it is made. The page only draws it.

The measures. For each, two windows of two regions:
  strong   the kind of coupling that measure is built to see, clearly there
  none     the same signals with that coupling taken out: independent
The statistics. Each simulated from cue-pair values up, through the pooling:
  agree      a change every rat shows, and the same mean change split 5:3
  outlier    seven rats unchanged and one changed hugely
  minus_fp   a change that is in the cue windows AND in rest, raw vs minus FP
  null       66 region pairs, nothing changed: what passes p < .05 anyway
  day        one rat's day: its cue pairs, mean and SE, beside its rest
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

import numpy as np                                         # noqa: E402

from backend import monolith as MO, sweep                  # noqa: E402

FS = 1000.0
N = 10000                      # a 10 s window
SNIP = 2.0                     # seconds of trace the figures show
RATS = [3, 4, 6, 7, 8, 9, 10, 11]
PAIRS = 15


def pink(rng, n, scale):
    """Noise with a 1/f-ish spectrum, as an LFP has."""
    w = rng.standard_normal(n)
    f = np.fft.rfftfreq(n, 1.0 / FS)
    F = np.fft.rfft(w) / np.maximum(f, 1.0) ** 0.5
    x = np.fft.irfft(F, n=n)
    return x / x.std() * scale


def rhythm(rng, n, hz, amp=1.0, jitter=2.0, breathe=0.5):
    """A rhythm whose phase wanders and whose size breathes, like theta.
    `jitter` 2 lets two unrelated rhythms drift apart within a second or so;
    at 0.6 they stayed in step for most of a 10 s window by chance, and
    "no coupling" read as a PLV of 0.70."""
    t = np.arange(n) / FS
    drift = np.cumsum(rng.standard_normal(n)) * jitter * 2 * np.pi * hz / FS
    env = 1.0 + breathe * np.sin(2 * np.pi * 0.3 * t + rng.uniform(0, 6.28))
    return amp * env * np.sin(2 * np.pi * hz * t + drift)


def slow_env(rng, n, depth=3.0):
    """A slow (< 1 Hz) swelling and fading, log-normal so it never goes
    negative: what makes two regions' 8 Hz loud and quiet together."""
    from scipy.signal import butter, sosfiltfilt
    e = sosfiltfilt(butter(2, 1.0 / (FS / 2), output="sos"),
                    rng.standard_normal(n))
    return np.exp(depth * 0.33 * e / e.std())


def band_noise(rng, n, lo=6.5, hi=9.5):
    """Band-limited noise: an 8 Hz rhythm whose own size wanders, as a real
    one does -- not a pure tone, whose envelope would be flat."""
    from scipy.signal import butter, sosfiltfilt
    x = sosfiltfilt(butter(4, [lo / (FS / 2), hi / (FS / 2)], btype="band",
                           output="sos"), rng.standard_normal(n))
    return x / x.std()


def shift(x, ms):
    k = int(round(ms * FS / 1000.0))
    return np.concatenate([np.zeros(k), x[:-k]]) if k > 0 else x


def scenario(name, strong, rng):
    """Two traces for one measure's demo."""
    na, nb = pink(rng, N, 40), pink(rng, N, 40)
    if name == "zero_lag":                  # coherence, PLV, PPC
        s = rhythm(rng, N, 8, 60)
        other = rhythm(rng, N, 8, 60)
        return (s + na, (s if strong else other) + nb)
    if name == "lagged":                    # icoh, PLI, wPLI, dwPLI
        s = rhythm(rng, N, 8, 60)
        other = rhythm(rng, N, 8, 60)
        return (s + na, (shift(s, 30) if strong else other) + nb)
    if name == "raw_cc":
        s = rhythm(rng, N, 8, 60) + pink(rng, N, 30)
        return (s + na, (0.8 * shift(s, 20) if strong else
                         rhythm(rng, N, 8, 60) + pink(rng, N, 30)) + nb)
    if name == "envelope":                  # envelope r, zero-lag r, orth
        # Unrelated 8 Hz waves; only the slow swelling and fading they are
        # multiplied by is shared (or not). Measured over ten windows: the
        # zero-lag envelope r is 0.68 +/- 0.32 when shared, 0.10 +/- 0.35
        # when not, and PLV barely differs (0.25 vs 0.19) -- loudness can be
        # shared with no phase relationship at all.
        e1 = slow_env(rng, N)
        e2 = e1 if strong else slow_env(rng, N)
        return (60 * e1 * band_noise(rng, N) + na * 0.25,
                60 * e2 * band_noise(rng, N) + nb * 0.25)
    if name == "granger":                   # a drives b, 10 ms late
        a = pink(rng, N, 50) + rhythm(rng, N, 8, 40)
        return (a + na * 0.3, (0.9 * shift(a, 10) if strong else
                               pink(rng, N, 50) + rhythm(rng, N, 8, 40)) + nb)
    if name == "power":
        return ((rhythm(rng, N, 8, 120) if strong else 0) + na,
                rhythm(rng, N, 8, 30) + nb)
    if name == "pac":
        t = np.arange(N) / FS
        th = np.sin(2 * np.pi * 6 * t + np.cumsum(rng.standard_normal(N))
                    * 0.01)
        gam = np.sin(2 * np.pi * 40 * t)
        mod = (1 + 0.9 * th) if strong else 1.0
        return (60 * th + 15 * mod * gam + na * 0.4,
                15 * mod * gam + 40 * rhythm(rng, N, 6) * 0.2 + nb * 0.4)
    raise ValueError(name)


SCENARIO = {"coherence": "zero_lag", "plv": "zero_lag", "ppc": "zero_lag",
            "icoh": "lagged", "pli": "lagged", "wpli": "lagged",
            "dwpli": "lagged", "raw_cc": "raw_cc", "env_cc": "envelope",
            "env_cc0": "envelope", "orth_env": "envelope",
            "gc_ab": "granger", "gc_ba": "granger", "gc_net": "granger",
            "power": "power", "pac": "pac"}
SAY = {
    "zero_lag": ("Both regions carry the same 8 Hz rhythm, plus their own noise.",
                 "Each region has its own 8 Hz rhythm; the two are unrelated."),
    "lagged": ("Both carry the same 8 Hz rhythm, the second 30 ms behind the first.",
               "Each region has its own 8 Hz rhythm; the two are unrelated."),
    "raw_cc": ("The second region is a copy of the first, 20 ms later, in noise.",
               "Two unrelated signals with the same kind of spectrum. Note how "
               "big the peak still is: two narrow-band signals line up "
               "somewhere within two cycles by chance, so a raw cc is only "
               "meaningful as a change between days."),
    "envelope": ("Different 8 Hz waves, but they grow and fade together.",
                 "Different 8 Hz waves that grow and fade on their own."),
    "granger": ("The first region drives the second, 10 ms later.",
                "Two unrelated signals."),
    "power": ("A strong 8 Hz rhythm in the first region.",
              "No 8 Hz rhythm to speak of in the first region."),
    "pac": ("Gamma (40 Hz) in both regions swells at one phase of the first "
            "region's 6 Hz theta.", "Gamma of steady size: no phase drives it."),
}


KEEP = ("t", "raw_a", "raw_b", "band_a", "band_b", "env_a", "env_b",
        "dphi", "orth_b")


def r3(x):
    """Three significant digits, everywhere in a structure."""
    if isinstance(x, float):
        return float("%.3g" % x)
    if isinstance(x, list):
        return [r3(v) for v in x]
    if isinstance(x, dict):
        return {k: r3(v) for k, v in x.items()}
    return x


def trim(ex):
    """What a figure needs from sweep.explain: the curves in full, the
    traces cut to SNIP seconds."""
    tr = ex["traces"]
    k = int(SNIP * tr["fs"])
    out = {"values": ex["values"], "power": ex["power"],
           "band": {k2: ex["band"][k2] for k2 in ("id", "low", "high",
                                                   "label", "lag_s")},
           "traces": dict({key: tr[key][:k] for key in KEEP if key in tr},
                          fs=tr["fs"])}
    for key in ("spectra", "granger", "phase", "segments", "lags", "orth",
                "pac"):
        if key in ex:
            out[key] = ex[key]
    return r3(out)


#: The number each scenario's representative window is chosen by.
KEY = {"zero_lag": "coherence", "lagged": "wpli", "raw_cc": "raw_cc",
       "envelope": "env_cc0", "granger": "gc_ab", "power": None, "pac": None}
CANDIDATES = 7


def scenarios(rng):
    """{scenario: {say, strong, none}}: each computed once, every measure
    that uses it reading its own number from it.

    One window is noisy, so each case draws CANDIDATES windows and shows the
    one whose key number is the median of them: a typical window, neither
    the luckiest nor the worst."""
    cell = next(i for i, c in enumerate(sweep.PAC_CELLS)
                if c[0] == 6 and c[1] == 40)
    out = {}
    mi = {m: i for i, m in enumerate(sweep.EDGE_METHODS)}
    for scen in dict.fromkeys(SCENARIO.values()):
        pair = {"say": {"strong": SAY[scen][0], "none": SAY[scen][1]}}
        band = "f08" if scen != "granger" else "f10"
        for case in ("strong", "none"):
            cands = [scenario(scen, case == "strong", rng)
                     for _ in range(CANDIDATES if KEY[scen] else 1)]
            if KEY[scen]:
                vals = []
                for a, b in cands:
                    v, _p, _n = sweep.window_measures([a, b], [band])
                    vals.append(float(v[0, mi[KEY[scen]], 0]))
                order = np.argsort(vals)
                a, b = cands[int(order[len(order) // 2])]
            else:
                a, b = cands[0]
            pair[case] = trim(sweep.explain(a, b, band, cell=cell))
        out[scen] = pair
    return out


# -------------------------------------------------------------- statistics
def days_of(rng, change, rest_change=0.0, per_rat=None, sd=0.06, base=0.4):
    """{(rat, day): (cue values (15,), rest values (8,))} with a given
    Precon1 -> Precon4 change (per rat if `per_rat`)."""
    out = {}
    for i, rat in enumerate(RATS):
        lvl = base + rng.normal(0, 0.05)
        d = per_rat[i] if per_rat is not None else change
        for day, add, radd in (("Precon1", 0.0, 0.0),
                               ("Precon4", d, rest_change)):
            cue = lvl + add + rng.normal(0, sd, PAIRS)
            rest = lvl - 0.05 + radd + rng.normal(0, sd, 8)
            out[(rat, day)] = (cue, rest)
    return out


def pooled_of(days, layer):
    """The real pipeline: day_stats per rat-day, layer_changes, pool."""
    cue = {k: tuple(np.asarray(x) for x in MO.day_stats(v[0][:, None]))
           for k, v in days.items()}
    rest = {k: tuple(np.asarray(x) for x in MO.day_stats(v[1][:, None]))
            for k, v in days.items()}
    rats, Y, V = MO.layer_changes(cue, rest, layer)
    got = MO.pool(Y, V)
    est, p = float(got["est"][0]), float(got["p"][0])
    se = float(got["se"][0])
    from scipy.stats import t as _t
    k = int(got["k"][0])
    half = float(_t.ppf(0.975, k - 1)) * se if math.isfinite(se) else None
    rows = []
    for i, rat in enumerate(rats):
        y, v = float(Y[i, 0]), float(V[i, 0])
        if not math.isfinite(y):
            continue
        rows.append({"rat": "r%d" % rat, "delta": y,
                     "ci": [y - 1.96 * math.sqrt(v), y + 1.96 * math.sqrt(v)],
                     "left": float(np.mean(days[(rat, "Precon1")][0])) - (
                         float(np.mean(days[(rat, "Precon1")][1]))
                         if layer == "minus_fp" else 0.0),
                     "right": float(np.mean(days[(rat, "Precon4")][0])) - (
                         float(np.mean(days[(rat, "Precon4")][1]))
                         if layer == "minus_fp" else 0.0),
                     "w": 1.0 / max(v, 1e-12)})
    tot = sum(r["w"] for r in rows)
    for r in rows:
        r["weight"] = r.pop("w") / tot
    return {"est": est, "p": p if math.isfinite(p) else None,
            "ci": [est - half, est + half] if half else None,
            "k": k, "same": int(got["same"][0]), "rats": rows}


def statistics(rng):
    out = {}
    agree = pooled_of(days_of(rng, 0.06), "raw")
    split_d = [0.25, 0.20, 0.16, 0.12, 0.10, -0.06, -0.10, -0.19]
    split = pooled_of(days_of(rng, 0.0, per_rat=split_d), "raw")
    out["agree"] = {"agree": agree, "split": split,
                    "say": "Both have about the same mean change. When every rat "
                           "moves the same way the test is confident; split "
                           "5:3, the same mean is not convincing."}
    lone = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.45]
    out["outlier"] = {"outlier": pooled_of(days_of(rng, 0.0, per_rat=lone),
                                           "raw"),
                      "say": "One rat with a huge change pulls the mean up, but "
                             "the others did not move: 1 of 8 the same way, and "
                             "the random-effects pool widens its interval."}
    both = days_of(rng, 0.10, rest_change=0.10)
    out["minus_fp"] = {"raw": pooled_of(both, "raw"),
                       "minus_fp": pooled_of(both, "minus_fp"),
                       "say": "The cue windows rose by 0.10 -- and so did rest. Raw "
                              "says something changed; minus FP says it was not "
                              "about the cues."}
    regions = sweep.regions()
    pairs = sweep.pairs_of(list(range(len(regions))))
    passed, tested = [], 0
    for pi, (a, b) in enumerate(pairs):
        r = pooled_of(days_of(rng, 0.0), "raw")
        tested += 1
        if r["p"] is not None and r["p"] < 0.05:
            passed.append({"pair": pi, "a": a, "b": b, "est": r["est"],
                           "p": r["p"], "same": r["same"]})
    out["null"] = {"regions": regions, "pairs": [list(p) for p in pairs],
                   "passed": passed, "tested": tested,
                   "say": "Nothing changed between the days, yet %d of %d region "
                          "pairs pass p < .05 -- about the 5%% chance alone gives. "
                          "Every edge here is a false lead." % (len(passed),
                                                                 tested)}
    d = days_of(rng, 0.0)
    cue, rest = d[(3, "Precon4")]
    m, s2, n = MO.day_stats(cue[:, None])
    rm, rs2, rn = MO.day_stats(rest[:, None])
    out["day"] = {"cue": [float(x) for x in cue], "rest": [float(x) for x in rest],
                  "mean": float(m[0]), "se": float(math.sqrt(s2[0])),
                  "rest_mean": float(rm[0]), "rest_se": float(math.sqrt(rs2[0])),
                  "say": "One rat's day: one dot per cue pair, the bar is the "
                         "day's mean and the whiskers its standard error."}
    return out


def main():
    rng = np.random.default_rng(20261002)
    data = {"schema": "arc.monolith.guide/1",
            "made_by": "tools/monolith_guide.py, with backend/sweep.py and "
                       "backend/monolith.py",
            "shape": {"fs": FS, "window_s": N / FS, "rats": len(RATS),
                      "cue_pairs_a_day": PAIRS, "snip_s": SNIP},
            "measures": SCENARIO, "scenarios": scenarios(rng),
            "stats": r3(statistics(rng))}
    out = os.path.join(APP, "web", "monolith_guide.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print("wrote %s (%d KB)" % (out, os.path.getsize(out) // 1024))
    for m, scen in data["measures"].items():
        v = data["scenarios"][scen]
        sv, nv = v["strong"]["values"], v["none"]["values"]
        if m in sv:
            print("  %-10s strong %8.3f   none %8.3f" % (m, sv[m], nv[m]))
    st = data["stats"]
    print("  agree p %.2g (%d/8)  split p %.2g (%d/8)" % (
        st["agree"]["agree"]["p"], st["agree"]["agree"]["same"],
        st["agree"]["split"]["p"], st["agree"]["split"]["same"]))
    print("  outlier est %.3f p %.2g same %d" % (
        st["outlier"]["outlier"]["est"], st["outlier"]["outlier"]["p"],
        st["outlier"]["outlier"]["same"]))
    print("  minus_fp raw p %.2g, minus p %.2g" % (
        st["minus_fp"]["raw"]["p"], st["minus_fp"]["minus_fp"]["p"]))
    print("  null: %d of %d pass" % (len(st["null"]["passed"]), st["null"]["tested"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
