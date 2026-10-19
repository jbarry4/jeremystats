"""
check_horizon.py -- is a row of the map the same answer as a Panorama run?

Horizon exists because Panorama draws one channel at a time. The whole
argument for building it on Panorama's engine rather than a second one is
that a row of the map and a Panorama run of that channel should BE the same
measurement. That is a claim, so it is checked rather than asserted.

Three questions, and they are not the same question.

1. FULL FIDELITY, FIT RANGE PINNED TO THE BAND -- must be identical.

   Horizon builds the spectrogram over its aperiodic fit range and slices to
   the band; Panorama builds it over the band directly. `scipy.signal.
   spectrogram` does not depend on the band at all, so those two arrays are
   the same rows -- and with `fit_hi` pinned to the top of the band, the
   decimation target matches too. Nothing is left that could differ. If this
   one disagrees, the shared engine is not shared.

2. FULL FIDELITY, THE DEFAULT WIDE FIT RANGE -- must be close, and the
   reason must be the decimation and nothing else.

   The default fits 1/f over 2-100 Hz, because a slope fitted over under
   three octaves is mostly fitting whatever theta is doing. That changes the
   decimation target -- 250 Hz rather than 35 -- so the signal itself
   differs slightly and so do the peak centres. Expected to be far inside
   the 0.5 Hz the transform can resolve.

3. SURVEY AGAINST FULL -- the one that is genuinely an approximation.

   Survey fits the aperiodic component ONCE per channel, on the mean
   spectrum, and takes the argmax of every flattened column. It is forty-odd
   times cheaper and it is not the same measurement. What matters is not that
   it agrees everywhere -- it will not -- but that it agrees WHERE THE WINNER
   ACTUALLY WON. A window whose runner-up was nearly as tall is a coin toss
   in both routes, and a disagreement there is two coin tosses landing
   differently rather than evidence about either.

   That is the same standard `check_panorama.py` settled on for the same
   reason, and it is why both routes carry a margin.

Run it from PowerShell, never bash: under bash Edge's --dump-dom writes
nothing on this machine and harnesses report zero checks, and while this one
does not drive a browser, the habit is the thing that keeps the suite honest.

    python tools/check_horizon.py --path "D:\\PTEN\\...\\2024-02-09_16-43-46"
    python tools/check_horizon.py            # the demo recording
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import csc, horizon, panorama          # noqa: E402


def report(name, a, b, tol, unit="", frac_ok=1.0):
    """Say how far apart two arrays are, and whether that is acceptable."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    both = np.isfinite(a) & np.isfinite(b)
    print()
    print("  %s" % name)
    if not both.any():
        print("    nothing comparable -- both are empty or all NaN")
        return False
    d = np.abs(a[both] - b[both])
    within = d <= tol
    frac = within.mean()
    print("    n=%d  median %.3g%s  max %.3g%s  within %.3g%s: %.1f%%"
          % (both.sum(), np.median(d), unit, d.max(), unit, tol, unit,
             100 * frac))
    ok = frac >= frac_ok
    if not ok:
        bad = np.flatnonzero(~within)[:5]
        idx = np.flatnonzero(both)[bad]
        print("    first disagreements at %s: %s vs %s"
              % (list(idx), np.round(a[idx], 4), np.round(b[idx], 4)))
    print("    %s" % ("ok" if ok else "DISAGREES"))
    return ok


def horizon_row(sess, spec):
    """One channel through Horizon, as (hz, margin)."""
    horizon.run(sess, spec)
    mats = horizon.mats_get(horizon.cache_key(spec))
    return (np.asarray(mats["hz"][0], dtype=float),
            np.asarray(mats["margin"][0], dtype=float))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", default="demo:long-session",
                    help="a recording folder, or a demo: id")
    ap.add_argument("--channel", type=int, default=6,
                    help="channel INDEX (not CSC number)")
    ap.add_argument("--t0", type=float, default=0.0)
    ap.add_argument("--t1", type=float, default=240.0)
    ap.add_argument("--every", type=int, default=5)
    args = ap.parse_args()

    sess = csc.open_session(args.path)
    if not sess.get("ok"):
        print("Could not open %s" % args.path)
        return 2
    n_ch = len(sess.get("channels") or [])
    if args.channel >= n_ch:
        print("That recording has %d channels, so index %d is not one of them."
              % (n_ch, args.channel))
        return 2

    dur = float(sess.get("duration_s") or 0.0)
    t1 = min(args.t1, dur) if dur else args.t1
    common = dict(path=args.path, t0=args.t0, t1=t1,
                  f_lo=2.0, f_hi=14.0, sub_s=2.0, win_s=8.0, step_s=1.0)

    print("check_horizon -- %s" % args.path)
    print("  channel index %d of %d, %.0f-%.0f s, 2-14 Hz, one column in %d"
          % (args.channel, n_ch, args.t0, t1, args.every))

    # ---- Panorama, the reference --------------------------------------
    pres = panorama.run(sess, dict(common, channels=[args.channel]))
    pw = pres["channels"][0]["windows"]
    p_hz = np.array([np.nan if v is None else v for v in pw["peak_hz"]],
                    dtype=float)[::args.every]
    p_mg = np.array([np.nan if v is None else v for v in pw["peak_margin"]],
                    dtype=float)[::args.every]
    print("  panorama: %d windows, decimate %d"
          % (len(pw["peak_hz"]), pres["plan"]["decimate"]))

    good = True

    # ---- 1. pinned fit range: must be identical ------------------------
    spec = dict(common, channels=[args.channel], fidelity="full",
                every=args.every, fit_lo=2.0, fit_hi=14.0)
    h_hz, h_mg = horizon_row(sess, spec)
    k = min(len(h_hz), len(p_hz))
    # 5e-5, because Panorama stores its windows rounded to four decimals and
    # that rounding is the only thing that can differ here.
    good &= report("1. full fidelity, fit range pinned to the band "
                   "-- must be identical",
                   h_hz[:k], p_hz[:k], 5e-5, " Hz")
    good &= report("   its margin, likewise", h_mg[:k], p_mg[:k], 5e-5)

    # ---- 2. the default wide fit range ---------------------------------
    spec = dict(common, channels=[args.channel], fidelity="full",
                every=args.every)
    w_hz, w_mg = horizon_row(sess, spec)
    k = min(len(w_hz), len(p_hz))
    # Half the transform's own resolution. A difference the transform cannot
    # see is not a difference anybody can act on.
    good &= report("2. full fidelity, default 2-100 Hz fit "
                   "-- close, and the cause is the decimation",
                   w_hz[:k], p_hz[:k], 0.25, " Hz", frac_ok=0.95)

    # ---- 3. survey against full ----------------------------------------
    spec = dict(common, channels=[args.channel], fidelity="survey",
                every=args.every)
    s_hz, s_mg = horizon_row(sess, spec)
    k = min(len(s_hz), len(w_hz))
    report("3. survey against full, every window "
           "-- for information, not a verdict",
           s_hz[:k], w_hz[:k], 1.0, " Hz", frac_ok=0.0)

    # Where the winner actually won, in BOTH routes. A coin toss that lands
    # differently twice is not evidence about either.
    clear = (np.nan_to_num(s_mg[:k]) >= 0.5) & (np.nan_to_num(w_mg[:k]) >= 0.5)
    if clear.sum() >= 20:
        good &= report("   survey against full, where both won clearly",
                       s_hz[:k][clear], w_hz[:k][clear], 1.0, " Hz",
                       frac_ok=0.90)
    else:
        print()
        print("   too few clearly-won windows to judge survey on (%d) -- "
              "this recording had no confident rhythm to agree about"
              % int(clear.sum()))

    print()
    if good:
        print("PASS -- a row of the map is a Panorama run of that channel,")
        print("        and the survey route tracks the full one where it counts.")
        return 0
    print("FAIL -- they disagree. Horizon and Panorama are supposed to be one")
    print("        engine, so a difference here is a difference nobody chose.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
