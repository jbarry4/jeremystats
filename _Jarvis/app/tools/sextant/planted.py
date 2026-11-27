"""Plant probes and find them again (backend/sextant/checks.py).

    python tools/sextant/planted.py [n] [seed]

Writes web/seahorse/sextant/planted.json: each plant's errors and whether the
cloud's 95% ranges held it, and the summary the reveal quotes.
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, APP)

from backend.sextant import atlas as A  # noqa: E402
from backend.sextant import checks  # noqa: E402
from backend.sextant import solve as SV  # noqa: E402

WEB = os.path.join(APP, "web", "seahorse", "sextant")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def main(argv):
    n = int(argv[0]) if argv else 12
    seed = int(argv[1]) if len(argv) > 1 else 7
    # a lighter search than the real one (the same methods, fewer candidates)
    SV.N_TOP_COARSE, SV.N_TOP_FINE, SV.N_RANDOM = 500, 120, 250
    atl = A.load()
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        t0 = time.time()
        rows.append(checks.run_one(atl, rng, log=log))
        log("   plant %d of %d in %.0f s" % (i + 1, n, time.time() - t0))
    summ = {}
    for k in ("ap", "ml", "depth", "tilt_ml", "tilt_ap"):
        e = np.array([r[k]["err"] for r in rows])
        summ[k] = {"median_abs": round(float(np.median(np.abs(e))), 3),
                   "p90_abs": round(float(np.percentile(np.abs(e), 90)), 3),
                   "covered": round(float(np.mean([r[k]["covered"] for r in rows])), 2)}
    out = {"made": time.strftime("%Y-%m-%d %H:%M"), "n": n, "seed": seed, "summary": summ, "plants": rows,
           "note": "Inference precision when the atlas and pathway model are right; a floor, not a guarantee."}
    with open(os.path.join(WEB, "planted.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    for k, v in summ.items():
        log("%-8s median |error| %s, 90%% within %s, 95%% ranges held the plant %d%% of the time" % (
            k, v["median_abs"], v["p90_abs"], round(100 * v["covered"])))


if __name__ == "__main__":
    main(sys.argv[1:])
