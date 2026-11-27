"""Gather Sextant's evidence for every scanned recording.

    python tools/sextant/evidence_all.py            # all that are scanned
    python tools/sextant/evidence_all.py m2 m60     # just these

Writes GUI_logs/.cache/sextant/<gid>/evidence.npz (machine cache, ignored by
git). Skips a recording whose scan is not there yet.
"""
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, APP)

from backend import stratasteps as st  # noqa: E402
from backend.sextant import cohort, evidence  # noqa: E402

LOGS = os.path.join(APP, "GUI_logs")
OUT = os.path.join(LOGS, ".cache", "sextant")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def main(argv):
    st.configure(LOGS)
    force = "--force" in argv
    argv = [a for a in argv if not a.startswith("--")]
    for r in cohort.recordings(LOGS, only=set(argv) or None):
        p = os.path.join(OUT, r["gid"], "evidence.npz")
        if os.path.exists(p) and not force:
            log(r["mouse"], "evidence exists")
            continue
        if not os.path.exists(os.path.join(st.DIR, r["gid"], "lfp.npy")):
            log(r["mouse"], "not scanned yet")
            continue
        t0 = time.time()
        try:
            ev = evidence.gather(LOGS, r, log=log)
            ev["mouse"] = r["mouse"]
            evidence.save(p, ev)
            log(r["mouse"], "saved in %.0f s" % (time.time() - t0))
        except Exception:
            log(r["mouse"], "FAILED")
            traceback.print_exc()


if __name__ == "__main__":
    main(sys.argv[1:])
