# -*- coding: utf-8 -*-
"""Does the parameterisation recover what was put into it?

The only honest way to test a fitting algorithm is to build a spectrum whose
answer you already know and see whether the answer comes back. Real data
cannot do this: there is no ground truth for the exponent of a hippocampus,
so a fit that is confidently wrong on a recording looks exactly like a fit
that is right.

So: synthetic spectra, built as the model says they should be -- an aperiodic
component plus Gaussian peaks, with noise on top -- across a range of
exponents, knees, peak heights and widths that covers what an LFP actually
does. Then the same numbers are asked for back.

Also the cases that should fail, because an algorithm that always finds a
peak is worse than useless:

  * a spectrum with NO peak in it must not produce one of any height
  * a peak buried under the noise must not be reported as confident
  * line noise must not be fitted as a rhythm

Run: python tools/check_specparam.py
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import specparam                            # noqa: E402

RNG = np.random.default_rng(20260914)

FAILED = []


def ck(name, ok, detail=""):
    print("  %-5s %s%s" % ("ok" if ok else "FAIL", name,
                           "" if ok else "   [%s]" % detail))
    if not ok:
        FAILED.append(name)


def build(freqs, offset, exponent, knee=None, peaks=(), noise=0.0):
    """A spectrum that IS the model, so the answer is known exactly."""
    if knee:
        logp = offset - np.log10(knee + freqs ** exponent)
    else:
        logp = offset - exponent * np.log10(freqs)
    for cf, pw, bw in peaks:
        std = bw / 2.0
        logp = logp + pw * np.exp(-((freqs - cf) ** 2) / (2 * std ** 2))
    if noise:
        logp = logp + RNG.normal(0.0, noise, size=freqs.shape)
    return np.power(10.0, logp)


# 1-200 Hz at the resolution a real run produces: 8 s segments at 500 Hz.
FREQS = np.arange(1.0, 200.0, 500.0 / 4096)

BANDS = [
    {"name": "delta", "lo": 1.0, "hi": 4.0, "cf_lo": 1.5, "cf_hi": 3.5},
    {"name": "theta", "lo": 4.0, "hi": 12.0, "cf_lo": 5.0, "cf_hi": 9.5},
    {"name": "beta", "lo": 13.0, "hi": 30.0, "cf_lo": 15.0, "cf_hi": 28.0},
    {"name": "low gamma", "lo": 30.0, "hi": 60.0, "cf_lo": 33.0,
     "cf_hi": 57.0},
    {"name": "high gamma", "lo": 60.0, "hi": 120.0, "cf_lo": 65.0,
     "cf_hi": 115.0},
]


print("A straight 1/f slope, no rhythms")
for expo in (0.8, 1.5, 2.0, 2.5, 3.0):
    psd = build(FREQS, 4.0, expo, noise=0.02)
    got = specparam.fit(FREQS, psd, 1.0, 200.0, mode="fixed", bands=BANDS)
    ck("exponent %.1f recovered" % expo,
       got and abs(got["exponent"] - expo) < 0.05,
       got and "%.3f" % got["exponent"])
    # The important negative: no rhythm was put in, so none may come out.
    tallest = max([p["power_db"] for p in got["band_peaks"].values()] or [0])
    ck("  and no rhythm invented", tallest < 0.05, "%.3f dB" % tallest)

print()
print("A slope with a knee")
for knee_hz, expo in ((3.0, 2.0), (10.0, 2.5), (30.0, 1.8)):
    k = knee_hz ** expo
    psd = build(FREQS, 4.0, expo, knee=k, noise=0.02)
    got = specparam.fit(FREQS, psd, 1.0, 200.0, mode="knee", bands=BANDS)
    ck("knee at %g Hz recovered" % knee_hz,
       got and got.get("knee_hz") and abs(got["knee_hz"] - knee_hz) < knee_hz * 0.25,
       got and str(got.get("knee_hz")))
    ck("  exponent %.1f with it" % expo,
       got and abs(got["exponent"] - expo) < 0.15,
       got and "%.3f" % got["exponent"])

print()
print("A theta rhythm on a slope -- the case the tool exists for")
for cf, pw in ((6.0, 0.5), (8.0, 0.3), (8.0, 1.0), (9.0, 0.15)):
    psd = build(FREQS, 4.0, 2.0, peaks=[(cf, pw, 2.0)], noise=0.02)
    got = specparam.fit(FREQS, psd, 1.0, 200.0, mode="fixed", bands=BANDS)
    th = (got or {}).get("band_peaks", {}).get("theta")
    ck("%.0f Hz at %.2f dB found" % (cf, pw),
       th and abs(th["center_hz"] - cf) < 0.5,
       th and "%.2f Hz" % th["center_hz"])
    ck("  and its height is right",
       th and abs(th["power_db"] - pw) < 0.12,
       th and "%.3f vs %.2f" % (th["power_db"], pw))

print()
print("The same, with a knee under it -- where the naive fit lost theta")
# This is the real failure that was measured on CSC41: an unconstrained
# knee settles on top of the theta peak and absorbs it.
psd = build(FREQS, 4.0, 2.4, knee=8.0 ** 2.4, peaks=[(8.0, 0.5, 2.0)],
            noise=0.02)
got = specparam.fit(FREQS, psd, 1.0, 200.0, mode="knee", bands=BANDS)
th = (got or {}).get("band_peaks", {}).get("theta")
ck("theta survives a knee sitting on it",
   th and abs(th["center_hz"] - 8.0) < 1.0 and th["power_db"] > 0.25,
   th and "%.2f Hz at %.3f dB" % (th["center_hz"], th["power_db"]))

print()
print("Line noise must not become a rhythm")
psd = build(FREQS, 4.0, 2.0, peaks=[(8.0, 0.5, 2.0)], noise=0.02)
line = np.abs(FREQS - 60.0) <= 0.4
psd[line] *= 300.0
mask = np.abs(FREQS - 60.0) <= 2.0
got = specparam.fit(FREQS, psd, 1.0, 200.0, mode="fixed", bands=BANDS,
                    ignore=mask)
lg = got["band_peaks"].get("low gamma")
ck("the 60 Hz spike is not reported as low gamma",
   not lg or lg["power_db"] < 0.1, lg and "%.3f dB" % lg["power_db"])
ck("and theta is still found alongside it",
   got["band_peaks"].get("theta", {}).get("power_db", 0) > 0.35,
   "%.3f" % got["band_peaks"].get("theta", {}).get("power_db", 0))

print()
print("The fit must describe the data")
for expo, pk in ((2.0, [(8.0, 0.5, 2.0)]), (1.2, [(6.0, 0.3, 1.5),
                                                  (40.0, 0.2, 8.0)])):
    psd = build(FREQS, 4.0, expo, peaks=pk, noise=0.03)
    got = specparam.fit(FREQS, psd, 1.0, 200.0, mode="fixed", bands=BANDS)
    ck("r^2 over 0.95 for exponent %.1f" % expo,
       got and got["r_squared"] > 0.95,
       got and "%.4f" % got["r_squared"])
    ck("  and the model never diverges",
       got and got["r_squared"] <= 1.0
       and all(abs(p["power_db"]) < 10 for p in got["band_peaks"].values()),
       got and "r2 %.3f" % got["r_squared"])

print()
print("A peak under the noise must not be reported as real")
psd = build(FREQS, 4.0, 2.0, peaks=[(8.0, 0.02, 2.0)], noise=0.10)
got = specparam.fit(FREQS, psd, 1.0, 200.0, mode="fixed", bands=BANDS)
th = got["band_peaks"].get("theta")
ck("a 0.02 dB rhythm under 0.10 dB noise stays small",
   not th or th["power_db"] < 0.15, th and "%.3f dB" % th["power_db"])

print()
if FAILED:
    print("%d check(s) FAILED: %s" % (len(FAILED), ", ".join(FAILED)))
    raise SystemExit(1)
print("all good -- the fit returns what was put into it")
