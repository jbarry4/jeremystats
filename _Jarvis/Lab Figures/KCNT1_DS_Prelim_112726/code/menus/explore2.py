import os, sys
import numpy as np
sys.path.insert(0, os.environ.get("KBAT", "/gpfs2/scratch/sakhava1/kcnt1_prelim/battery"))
import dsdata
recs = dsdata.by_lab(dsdata.load("v6"))
for lab in ("m7", "m21", "m26", "m61", "m1", "m33", "m8"):
    r = recs[lab]
    w = r.W.get("both") if r.W else None
    zero_deg = None
    if w is not None:
        w = np.array(w, float); np.fill_diagonal(w, 0.0)
        zero_deg = int((w.sum(axis=1) <= 0).sum())
    t = r.types("winner") if r.has("winner") else None
    print(lab, "winner", r.winner, "si", r.winner_si, "n1", None if t is None else int((t == 1).sum()), "n2", None if t is None else int((t == 2).sum()),
          "W both", None if w is None else w.shape, "zero-degree events", zero_deg)
