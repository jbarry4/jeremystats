"""
check_panorama.py -- does the GUI give the numbers the command line gave?

Panorama is a port of `FOOOF Playgroun/theta_through_time.py`. The lab has
already run that script and has its numbers in notebooks, so the question
that matters is not "does Panorama run" but "does it agree". This asks, on a
real recording, and says where it does not.

MAKING THE TWO COMPARABLE FIRST

They do not match out of the box, and comparing them as they stand would
produce a disagreement that means nothing:

                    playground              Panorama, by default
  decimated rate    TARGET_FS = 250 Hz      target_rate(f_hi) -> 500 Hz at 200
  band              FMAX = 100, fit 2-45    2-200

`target_rate(100)` is exactly 250 Hz, so asking both for **2-100 Hz** puts
them on the same rate and the same band, and `--sub 2 --win 8 --step 1`
matches Panorama's defaults for the rest. That is what this runs.

WHAT IS COMPARED, AND WHAT DELIBERATELY IS NOT

  dom_all_hz   <-> windows.peak_hz    the tallest fitted peak. The headline
                                      number, and the one that has to agree.
  exponent     <-> windows.exponent
  r2           <-> windows.r2

NOT `dom_theta_hz` against `flat_hz`: the playground's is an argmax
restricted to 4-12 Hz and Panorama's is over the whole fit range. Different
questions, and a disagreement there would be correct behaviour.

AND THE DOMINANT FREQUENCY IS JUDGED WHERE IT MEANS SOMETHING

Measured on M1ptens2oct2: the two disagree about the dominant frequency in
9.4% of windows. Chunk edges do not explain it (31% of disagreements near
one, against 23% of all windows) and neither does the recording's gap (1 of
160). What does: in those windows the other's answer is a peak in this one's
fit too, at a median 0.947 of the winner's power, and only 5 of the 160 are
below 12 Hz -- the median is 43.8 Hz, in the broad bumps a 1/f spectrum has
across the gamma range. Theta, the rhythm anybody is actually asking about,
is essentially never in dispute.

So the two are not disagreeing about the spectrum. They agree about it -- the
aperiodic exponent matches to a median of 0.002 -- and disagree about an
argmax over numbers that are equal to three significant figures. "Which of
two equally tall peaks is taller" is not a quantity, and a test that demands
they agree on it is testing floating point.

This therefore reports both: agreement everywhere, and agreement in the
windows where the winning peak actually won, by the margin Panorama records.
The second is the one that has to hold.

Usage:
    python tools/check_panorama.py [--folder <recording>] [--channel CSC1]
                                   [--minutes N]   (trim, for a quick check)
"""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
REPO = os.path.dirname(APP)
PLAYGROUND = os.path.join(REPO, "FOOOF Playgroun", "theta_through_time.py")

DEFAULT_FOLDER = r"D:\PTEN\PTEN\M1_Pten\M1ptens2oct2\2023-10-02_16-58-03"

# The settings that put both on the same footing. See the module note.
F_LO, F_HI = 2.0, 100.0

# A peak counts as a clear winner when the runner-up is this far below
# it, as a fraction of its own height. Below that the two implementations
# are choosing between numbers equal to three significant figures.
CLEAR_MARGIN = 0.2
SUB_S, WIN_S, STEP_S = 2.0, 8.0, 1.0

sys.path.insert(0, APP)


def run_playground(folder, channel, out_csv):
    """The original script, with its figure sent to a file.

    `--save` matters: without it the script ends in `plt.show()`, which
    blocks for ever with nobody to close the window.
    """
    fig = os.path.join(tempfile.gettempdir(), "panorama-check.png")
    cmd = [sys.executable, PLAYGROUND,
           "--folder", folder, "--channel", channel,
           "--sub", str(SUB_S), "--win", str(WIN_S), "--step", str(STEP_S),
           "--fit-lo", str(F_LO), "--fit-hi", str(F_HI),
           "--csv", out_csv, "--save", fig]
    env = dict(os.environ)
    env["MPLBACKEND"] = "Agg"        # belt as well as braces
    print("  $ " + " ".join(cmd[1:]))
    t0 = time.time()
    p = subprocess.run(cmd, cwd=os.path.dirname(PLAYGROUND), env=env,
                       capture_output=True, text=True)
    print("  (%.0f s)" % (time.time() - t0))
    if p.returncode != 0:
        print(p.stdout[-3000:])
        print(p.stderr[-3000:])
        raise SystemExit("the playground script failed")
    return out_csv


def read_playground(path):
    t, dom, expo, r2 = [], [], [], []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            t.append(float(row["t_s"]))
            dom.append(_f(row["dom_all_hz"]))
            expo.append(_f(row["exponent"]))
            r2.append(_f(row["r2"]))
    return (np.array(t), np.array(dom), np.array(expo), np.array(r2))


def _f(v):
    try:
        got = float(v)
    except (TypeError, ValueError):
        return np.nan
    return got


def run_panorama(folder, channel):
    from backend import csc, panorama

    sess = csc.open_session(folder)
    if not sess.get("ok"):
        raise SystemExit("could not open %s: %s" % (folder, sess.get("error")))
    want = channel.upper()
    ch = None
    for c in sess.get("channels") or []:
        if (c.get("label") or "").upper() == want:
            ch = c
            break
    if ch is None:
        raise SystemExit("no %s in that recording" % channel)

    spec = {"path": folder, "channels": [ch["index"]],
            "f_lo": F_LO, "f_hi": F_HI,
            "sub_s": SUB_S, "win_s": WIN_S, "step_s": STEP_S}
    plan = panorama.plan_for(sess, spec)
    print("  decimating %.0f -> %.0f Hz (the playground's own rate is 250)"
          % (plan["fs"], plan["fs_used"]))
    if abs(plan["fs_used"] - 250.0) > 1e-6:
        print("  !! rates differ; the comparison below is not apples to apples")
    t0 = time.time()
    out = panorama.run(sess, spec)
    print("  (%.0f s)" % (time.time() - t0))
    w = out["channels"][0]["windows"]

    def n(a):
        return np.array([np.nan if v is None else v for v in a], float)

    return (np.array(w["t_s"], float), n(w["peak_hz"]),
            n(w["exponent"]), n(w["r2"]), n(w["peak_margin"]))


def align(ta, tb, tol=0.02):
    """Index pairs whose times are the same window.

    Lengths can differ by a sample where the two readers trim the ends
    differently; matching on time rather than on position means a one-sample
    offset shows up as a shorter overlap instead of comparing every window
    with its neighbour and calling it a disagreement.
    """
    ia, ib = [], []
    j = 0
    for i, t in enumerate(ta):
        while j + 1 < len(tb) and abs(tb[j + 1] - t) <= abs(tb[j] - t):
            j += 1
        if abs(tb[j] - t) <= tol:
            ia.append(i)
            ib.append(j)
    return np.array(ia, int), np.array(ib, int)


def report(name, a, b, tol, unit=""):
    """How closely two columns agree, and whether that is good enough."""
    both = np.isfinite(a) & np.isfinite(b)
    neither = ~np.isfinite(a) & ~np.isfinite(b)
    only_a = np.isfinite(a) & ~np.isfinite(b)
    only_b = ~np.isfinite(a) & np.isfinite(b)
    d = np.abs(a[both] - b[both]) if both.any() else np.array([])
    ok = True
    print()
    print("  %s" % name)
    print("    both have a value : %d" % int(both.sum()))
    print("    neither does      : %d" % int(neither.sum()))
    if only_a.sum() or only_b.sum():
        print("    only one does     : %d playground, %d Panorama"
              % (int(only_a.sum()), int(only_b.sum())))
    if d.size:
        print("    median difference : %.6g%s" % (float(np.median(d)), unit))
        print("    90th percentile   : %.6g%s"
              % (float(np.percentile(d, 90)), unit))
        print("    worst             : %.6g%s" % (float(d.max()), unit))
        agree = float(np.mean(d <= tol))
        print("    within %.4g%s      : %.2f%% of windows"
              % (tol, unit, 100 * agree))
        ok = agree >= 0.95
    # Disagreeing about whether there IS a peak is as much a disagreement as
    # disagreeing about where it is.
    if both.sum() + neither.sum():
        same_call = (both.sum() + neither.sum()) / float(len(a))
        print("    agree on whether there is one at all: %.2f%%"
              % (100 * same_call))
        ok = ok and same_call >= 0.95
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default=DEFAULT_FOLDER)
    ap.add_argument("--channel", default="CSC1")
    ap.add_argument("--keep", action="store_true",
                    help="keep the playground's CSV")
    args = ap.parse_args()

    if not os.path.isdir(args.folder):
        raise SystemExit("not a folder: %s" % args.folder)
    if not os.path.exists(PLAYGROUND):
        raise SystemExit("cannot find %s" % PLAYGROUND)

    print("Comparing Panorama with theta_through_time.py")
    print("  recording : %s" % args.folder)
    print("  channel   : %s" % args.channel)
    print("  settings  : %.4g-%.4g Hz, %.3g s transform, %.3g s window, "
          "%.3g s step" % (F_LO, F_HI, SUB_S, WIN_S, STEP_S))

    csv_path = os.path.join(tempfile.gettempdir(), "panorama-check.csv")
    print()
    print("the original")
    run_playground(args.folder, args.channel, csv_path)
    pt, pdom, pexp, pr2 = read_playground(csv_path)
    print("  %d windows" % len(pt))

    print()
    print("Panorama")
    gt, gdom, gexp, gr2, gmargin = run_panorama(args.folder, args.channel)
    print("  %d windows" % len(gt))

    ia, ib = align(pt, gt)
    print()
    print("  %d windows line up in time (of %d and %d)"
          % (len(ia), len(pt), len(gt)))
    if len(ia) < 0.9 * min(len(pt), len(gt)):
        print("  !! the time axes do not line up; everything below is suspect")

    good = True
    # The fits themselves. These have to agree: if they do not, nothing
    # below means anything.
    good &= report("aperiodic exponent", pexp[ia], gexp[ib], 0.05)
    good &= report("fit R-squared", pr2[ia], gr2[ib], 0.02)

    # A dominant frequency is read off a 0.5 Hz grid, so a disagreement
    # smaller than one bin is the two landing on the same bin.
    report("dominant frequency -- every window", pdom[ia], gdom[ib], 0.5,
           " Hz")

    m = gmargin[ib]
    clear = np.isfinite(m) & (m >= CLEAR_MARGIN)
    close = np.isfinite(m) & (m < CLEAR_MARGIN)
    print()
    print("  how clearly the winning peak won")
    print("    clear (runner-up more than %.0f%% below) : %d windows"
          % (100 * CLEAR_MARGIN, int(clear.sum())))
    print("    a close call                            : %d windows (%.1f%%)"
          % (int(close.sum()),
             100.0 * close.sum() / max(1, np.isfinite(m).sum())))
    print("    -- in a close call, neither answer is a finding; see the note")
    print("       at the top of this file.")
    if clear.sum() > 30:
        good &= report("dominant frequency -- where it won clearly",
                       pdom[ia][clear], gdom[ib][clear], 0.5, " Hz")
    else:
        print()
        print("  too few clear winners to judge the dominant frequency on "
              "(%d)" % int(clear.sum()))

    if not args.keep:
        try:
            os.remove(csv_path)
        except OSError:
            pass

    print()
    if good:
        print("PASS -- the GUI gives the numbers the command line gives.")
        return 0
    print("FAIL -- they disagree. A number out of Panorama is not the number")
    print("        already in somebody's notebook, and one of them is wrong.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
