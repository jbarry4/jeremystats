# -*- coding: utf-8 -*-
"""Does Doppler's production engine reproduce the study?

Runs `backend.doppler.run` -- the exact function a VACC node runs, with the
default Storm parameters from `doppler.params_from({})` -- on all ten PTEN
recordings, reading the raw .ncs the way the node does, and scores it
against the hand-sorts. The study's own number for this specification is
169/169 reachable Solids in 2,491 detections; the production engine computes
its threshold exactly (MATLAB's percentile on every value) where the study
used every tenth value, so a small difference in the count is expected and a
lost Solid is not.

    python validate_production.py            all ten, 3 at a time
    python validate_production.py m34_s5     one

A candidate other than the shipped defaults, without changing them:

    $env:SPEC='{"band": [20, 300], "llw_s": 0.015, "min_channels": 7}'

The hand-sorted stamps are on CONCATENATED time (they came from the
MATLAB's sample index) and the engine answers on the recording's own clock,
so each stamp is moved onto the recording's clock before matching. Without
that a Solid after a 125 ms acquisition pause scores as missed when it was
found -- which is what the first run of this reported for M34 s8.
"""
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import ied_common as C


def one(rec):
    from backend import continuity, csc, doppler
    from step3_sweep import vmatch
    t0 = time.time()
    sess = csc.open_session(rec["folder"], invert=True)
    rep = continuity.check(rec["folder"])
    bad = set(rec["bad"])
    spec = dict(doppler.params_from(json.loads(os.environ.get("SPEC") or "{}")),
                path=rec["folder"],
                channels=[c["index"] for c in sess["channels"]
                          if int(c["number"]) not in bad],
                bad_channels=sorted(bad), excluded=[], banks=None,
                invert=True)
    out = doppler.run(sess, spec, rep, None)
    ev = np.asarray([[e["start"] - 0.05, (e["end"] or e["start"]) + 0.05]
                     for e in out["events"]]) if out["events"] else np.zeros((0, 2))
    seconds = float(rep.get("true_duration_s") or out.get("duration_s") or 1e9)
    res = {"key": rec["key"], "n_det": len(out["events"]),
           "threshold": out["params"]["threshold"],
           "seconds": round(time.time() - t0, 1)}
    fs = float(rep.get("fs") or 30000.0)

    def on_clock(t):
        got = continuity.sample_to_true(rep, int(round(t * fs)))
        if got is None:
            got = continuity.concat_to_true(rep, t)[0]
        return t if got is None else got

    for lab in ("solid", "garbage", None):
        ts = np.asarray(sorted(on_clock(e["t"]) for e in rec["events"]
                               if e["label"] == lab and e["t"] <= seconds))
        m = vmatch(ev, ts, tol=C.MATCH_S)
        res[(lab or "unrev") + "_hit"] = int((m >= 0).sum())
        res[(lab or "unrev") + "_n"] = int(len(ts))
    res["gaps_s"] = round(float(rep.get("seconds_lost") or 0.0), 3)
    return res


def main():
    gt = C.load_gt()
    want = set(sys.argv[1:])
    recs = sorted([r for r in gt if not want or r["key"] in want],
                  key=lambda r: -(r.get("duration_s") or 0))
    rows = []
    with ProcessPoolExecutor(max_workers=3) as ex:
        for r in ex.map(one, recs):
            rows.append(r)
            C.log(r)
    tot = {k: sum(r[k] for r in rows) for k in rows[0] if k.endswith(("_hit", "_n"))
           or k == "n_det"}
    C.log("\nTOTAL", tot)
    C.log("Solids %d/%d in %d detections" % (tot["solid_hit"], tot["solid_n"],
                                             tot["n_det"]))
    name = os.environ.get("OUTNAME") or "validate_production"
    with open(os.path.join(C.OUT, name + ".json"), "w") as fh:
        json.dump({"spec": os.environ.get("SPEC") or "defaults", "rows": rows,
                   "total": tot}, fh, indent=1)


if __name__ == "__main__":
    main()
