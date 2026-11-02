"""
fooof_window_psd.py -- FOOOF power spectrum for one time window of one channel.

Power on the y axis, frequency on the x axis, with the FOOOF model
(aperiodic component + fitted peaks) drawn over the measured spectrum.

Defaults to 200-300 s of CSC1 from
  D:/PTEN/PTEN/M1_Pten/M1ptens2oct2/2023-10-02_16-58-03

Run:
  python fooof_window_psd.py
  python fooof_window_psd.py --channel CSC7 --start 200 --stop 300
  python fooof_window_psd.py --fmin 1 --fmax 55 --save spectrum.png
"""

import argparse
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import welch

from fooof import FOOOF

# The lab's own .ncs reader -- same ADBitVolts scaling and polarity convention
# the rest of the pipeline uses, and it seeks to the window instead of reading
# the whole 100 MB file.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "BARRY GUI", "backend"))
from nlx import read_ncs_range  # noqa: E402

FOLDER = r"D:/PTEN/PTEN/M1_Pten/M1ptens2oct2/2023-10-02_16-58-03"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folder", default=FOLDER, help="session folder")
    ap.add_argument("--channel", default="CSC1", help="channel, e.g. CSC1")
    ap.add_argument("--start", type=float, default=200.0, help="window start (s)")
    ap.add_argument("--stop", type=float, default=300.0, help="window end (s)")
    ap.add_argument("--fmin", type=float, default=1.0, help="low edge of fit (Hz)")
    ap.add_argument("--fmax", type=float, default=55.0, help="high edge of fit (Hz)")
    ap.add_argument("--seglen", type=float, default=4.0,
                    help="Welch segment length (s); sets frequency resolution")
    ap.add_argument("--save", default=None, help="write the figure here instead of showing it")
    args = ap.parse_args()

    path = os.path.join(args.folder, args.channel + ".ncs")
    if not os.path.exists(path):
        sys.exit("no such file: " + path)

    # --- 1. the window ----------------------------------------------------
    # Times are seconds from the first record, which is where the recording's
    # own clock starts. A window crossing a Cheetah gap comes back short
    # rather than padded, so report what was actually read.
    gaps = {}
    data, t0_actual, fs = read_ncs_range(path, args.start, args.stop, report=gaps)
    if data.size == 0:
        sys.exit("window %.1f-%.1f s is empty" % (args.start, args.stop))

    # read_ncs_range returns whole records, so trim to the requested edges.
    i0 = int(round((args.start - t0_actual) * fs))
    i1 = i0 + int(round((args.stop - args.start) * fs))
    data = data[max(0, i0):i1]

    print("%s  fs=%.1f Hz  %.2f s read (%d samples)"
          % (args.channel, fs, data.size / fs, data.size))
    if gaps.get("gaps"):
        print("  note: window crosses %d discontinuity(ies)" % len(gaps["gaps"]))

    # --- 2. the power spectrum -------------------------------------------
    nperseg = int(args.seglen * fs)
    freqs, powers = welch(data, fs=fs, nperseg=nperseg, noverlap=nperseg // 2)
    print("  Welch: %.1f s segments -> %.3f Hz resolution" % (args.seglen, freqs[1]))

    # --- 3. the FOOOF fit -------------------------------------------------
    fm = FOOOF(peak_width_limits=[1.0, 12.0], max_n_peaks=6,
               min_peak_height=0.05, aperiodic_mode="fixed", verbose=False)
    fm.fit(freqs, powers, [args.fmin, args.fmax])
    fm.print_results()

    # --- 4. the plot: power (y) against frequency (x) ---------------------
    fig, ax = plt.subplots(figsize=(8, 5.5))
    fm.plot(ax=ax, plt_log=False)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("log10 power ($\\mu V^2$/Hz)")
    ax.set_title("%s  %s  %g-%g s" % (os.path.basename(args.folder),
                                      args.channel, args.start, args.stop))
    fig.tight_layout()

    if args.save:
        fig.savefig(args.save, dpi=150)
        print("  wrote " + args.save)
    else:
        plt.show()


if __name__ == "__main__":
    main()
