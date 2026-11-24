"""Reader parity for the Cells (PROJECT EVOLVE phase 7, 2026-11-21).

For every recording on this computer with a Kilosort sort and Isabella's
export beside it:

  * every exported cell's samples equal `spike_times[spike_clusters == id]`
    of the NON-inverted run, exactly. How many ALSO equal the inverted
    twin's cluster of the same id is said, not failed: on 2026-11-21 13 of
    the 32 recordings had some (m10 s4, M7 s6: all), so for those the twin
    sorted those cells identically;
  * cells.true_seconds equals continuity.sample_to_true on a sample of
    each cell's spikes (to the microsecond);
  * the binary's length equals the continuity map's total samples.

Reads only. Run from the app folder:  python tools/test_cells.py [filter]
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
os.chdir(APP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

from backend import cells as C                          # noqa: E402
from backend import continuity                          # noqa: E402
from backend.paths import LOGS_DIR                      # noqa: E402

continuity.configure(LOGS_DIR)
ROOTS = [r"D:\PTEN"]


def sessions():
    for root in ROOTS:
        for dirpath, dirnames, _files in os.walk(root):
            if "binary" in dirnames and C.export_dir(dirpath):
                yield dirpath
            # Not below a recording.
            if os.path.isdir(os.path.join(dirpath, "binary")):
                dirnames[:] = []


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else ""
    n_rec = n_cells = bad = 0
    for path in sorted(sessions()):
        if want and want.lower() not in path.lower():
            continue
        run, twin = C.pick_run(path)
        if not run:
            print("no plain run  ", path)
            bad += 1
            continue
        cells = C.read_source(path, run["path"], "export")
        exact = C.check_against_run(run["path"], cells)
        tw = C.check_against_run(twin["path"], cells) if twin else 0
        rep = continuity.check(path)
        nbin = os.path.getsize(os.path.join(path, "binary", "CSC_Raw.dat")) // (C.N_CHAN * 2)
        worst = 0.0
        for s in cells.values():
            pick = s[:: max(1, len(s) // 200)]
            mine = C.true_seconds(rep, pick)
            ref = np.array([continuity.sample_to_true(rep, int(i)) for i in pick], dtype=float)
            worst = max(worst, float(np.nanmax(np.abs(mine - ref))) if len(pick) else 0.0)
        ok = (exact == len(cells) and worst < 1e-6
              and int(rep.get("total_samples") or 0) == nbin)
        bad += 0 if ok else 1
        n_rec += 1
        n_cells += len(cells)
        print("%s  %-70s cells %3d  exact %3d  twin same %d  time err %.1e s  binary %s"
              % ("ok  " if ok else "FAIL", path[-70:], len(cells), exact, tw, worst,
                 "= map" if int(rep.get("total_samples") or 0) == nbin else "!= map"))
    print("\n%d recordings, %d cells, %d failing" % (n_rec, n_cells, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
