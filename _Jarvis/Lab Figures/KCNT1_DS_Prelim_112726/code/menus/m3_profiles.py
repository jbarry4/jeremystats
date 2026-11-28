"""Story menu, step 3: each recording's dentate spike CSD and LFP (the room's X-ray reads, Halo and Strict sets) as
mean profiles at the peak, per contact. Used only as the reference for CSD polarity in m4_dsied.py. No layer labels:
the scale (ref) is the deepest sink on the dentate rows found from the spike itself (DS-registered depth within
0.6 blade-widths of the two main sinks). Writes profiles_ds.pkl.
"""
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.environ.get("KBAT", "/gpfs2/scratch/sakhava1/kcnt1_prelim/battery"))
import dsdata  # noqa: E402

out = {}
for es in ("v6", "v8"):
    recs = dsdata.load(es)
    for r in recs:
        if r.lab in ("m6", "m51"):
            continue
        bad = list(r.bad_rows)
        peak = np.nanmean(np.asarray(r.csd_peak, float), axis=0)
        peak = dsdata.fill_bad(peak, bad) if bad else peak
        ref = np.nan
        if r.landmarks is not None:
            u = r.u(np.arange(peak.size))
            dg = (u >= -0.6) & (u <= 1.6)
            ref = -np.nanmin(np.where(dg, peak, np.nan))
        d = {"lab": r.lab, "n": int(r.n), "t_ms": np.asarray(r.t_ms, float), "peak": peak, "ref": ref, "bad": bad,
             "winner": r.winner, "winner_si": r.winner_si, "times_s": np.asarray(r.times_s, float)}
        out[(es, r.lab)] = d
        print(es, r.lab, r.n, "ref %.3g" % ref, flush=True)
    del recs
with open(os.path.join(HERE, "profiles_ds.pkl"), "wb") as f:
    pickle.dump(out, f, protocol=4)
print("saved")
