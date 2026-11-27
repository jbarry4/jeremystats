"""Place every recording that has evidence (Method A for now).

    python tools/sextant/place.py              # all with evidence
    python tools/sextant/place.py m2 m60       # these

Writes GUI_logs/.cache/sextant/<gid>/placement.json and prints a table.
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
from backend.sextant import cohort, detectors, evidence, fit  # noqa: E402

LOGS = os.path.join(APP, "GUI_logs")
OUT = os.path.join(LOGS, ".cache", "sextant")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def summarize(atl, rec, lms, notes, res, n_cloud=60):
    w = fit.posterior(res)
    order = np.argsort(-(-0.5 * res["chi2"] + res["lp"]))
    best = int(order[0])
    pose = fit.pose_of(res, best)
    d = fit.describe(atl, pose, rec["hemisphere"])
    rng = np.random.default_rng(0)
    idx = rng.choice(w.size, 400, p=w)
    eps = [fit.describe(atl, fit.pose_of(res, j), rec["hemisphere"]) for j in idx]

    def rng_of(vals):
        v = np.asarray(vals, float)
        return [round(float(np.percentile(v, 2.5)), 3), round(float(np.median(v)), 3),
                round(float(np.percentile(v, 97.5)), 3)]
    ranges = {
        "entry_ap": rng_of([e["entry"]["ap"] for e in eps]),
        "entry_ml": rng_of([e["entry"]["ml"] for e in eps]),
        "tilt_ml": rng_of([e["tilt_ml"] for e in eps]),
        "tilt_ap": rng_of([e["tilt_ap"] for e in eps]),
        "scale": rng_of([e["scale"] for e in eps]),
        "depth64": rng_of([e["depth_um"]["contact64"] for e in eps]),
    }
    o, s = res["o"][best], res["s"][best]
    resid = []
    for l in lms:
        if l["key"] not in fit.MATCH:
            continue
        L_ = res["alm"][fit.MATCH[l["key"]][0]][best]
        pred = (L_ - o) / (fit.PITCH * s) if np.isfinite(L_) else None
        resid.append({"key": l["key"], "found": round(l["x"], 2), "sigma": l["sigma"],
                      "atlas": None if pred is None else round(float(pred), 2)})
    cloud = []
    for j in idx[:n_cloud]:
        p = fit.pose_of(res, j)
        pts = A.contacts(p["centre"], p["dir"], p["scale"])
        cloud.append([[round(float(x), 1) for x in pts[0]], [round(float(x), 1) for x in pts[-1]]])
    return {"gid": rec["gid"], "mouse": rec["mouse"], "group": rec["group"],
            "hemisphere": rec["hemisphere"], "method": "A",
            "best": d, "chi2": round(float(res["chi2"][best]), 3),
            "ranges": ranges, "landmarks": lms, "notes": notes, "residuals": resid,
            "cloud": cloud, "n_lines": int(res["chi2"].size)}


def main(argv):
    atl = A.load()
    rows = []
    for rec in cohort.recordings(LOGS, only=set(argv) or None):
        p = os.path.join(OUT, rec["gid"], "evidence.npz")
        if not os.path.exists(p):
            continue
        ev = evidence.load(p)
        lms, notes = detectors.detect(ev)
        t0 = time.time()
        res = fit.search(atl, lms, log=lambda *a: None)
        out = summarize(atl, rec, lms, notes, res)
        with open(os.path.join(OUT, rec["gid"], "placement.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1, default=float)
        b, r = out["best"], out["ranges"]
        rows.append((rec["mouse"], rec["group"], rec["hemisphere"], b["entry"]["ap"], b["entry"]["ml"],
                     b["tilt_ml"], b["tilt_ap"], b["scale"], b["depth_um"]["contact64"], out["chi2"],
                     len([l for l in lms if l["key"] in fit.MATCH]), r))
        log(rec["mouse"], "placed in %.0f s" % (time.time() - t0))
    print()
    print("mouse grp side  entryAP  entryML  tiltML tiltAP scale  tip_um  chi2  n | AP 95%%           ML 95%%")
    for m, g, h, ap, ml, tm, ta, s, dp, c2, n, r in rows:
        print("%-5s %-4s %-4s %7.2f %8.2f %7.1f %6.1f %5.2f %7d %5.1f %2d | %5.2f..%5.2f  %5.2f..%5.2f" % (
            m, g, h, ap, ml, tm, ta, s, dp, c2, n, r["entry_ap"][0], r["entry_ap"][2], r["entry_ml"][0], r["entry_ml"][2]))


if __name__ == "__main__":
    main(sys.argv[1:])
