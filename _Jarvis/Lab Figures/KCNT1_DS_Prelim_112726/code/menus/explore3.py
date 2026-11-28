import os, sys
import numpy as np
sys.path.insert(0, os.environ.get("KBAT", "/gpfs2/scratch/sakhava1/kcnt1_prelim/battery"))
import dsdata
recs = dsdata.by_lab(dsdata.load("v6"))
for lab in ("m13", "m28", "m3", "m5", "m34"):
    z = np.load(os.path.join("reads", lab + ".npz"), allow_pickle=True)
    nums = [int(x) for x in z["nums"]]
    c = list(recs[lab].contacts)
    print(lab, "same order" if nums == c else "DIFFERENT", len(nums), len(c), nums[:4], c[:4], "bad reads", list(z["bad"]), "bad battery", recs[lab].bad)
for lab in ("m7", "m26", "m61", "m1", "m2", "m13"):
    k = recs[lab].landmarks
    print(lab, "src_rows", k["src_rows"], "rowU", k["rowU"], "rowL", k["rowL"], "rowGU", k["rowGU"], "rowGL", k["rowGL"], "band", recs[lab].band, "cut", recs[lab].hump_cut_row)
