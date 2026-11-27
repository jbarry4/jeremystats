import os, sys, pickle
import numpy as np
sys.path.insert(0, os.getcwd())
import menu_data as D
ids = ["laminar|net_between_median|v6|winner|ds1", "structure|overlap_eig2|v6||overlap", "timing|iei_median|v6|winner|ds2",
       "rootcanal|ds_hf_median|v6||"]
for mid in ids:
    v = D.values(mid)
    print(mid, "m7" in v, {k: round(x, 3) for k, x in v.items()})
U = pickle.load(open("uprof.pkl", "rb"))
G = U["UGRID"]
print("rec keys", list(U["recs"][("v6", "m2")].keys()))
for lab in D.LABS16:
    r = U["recs"].get(("v6", lab))
    if r is None:
        print(lab, "none"); continue
    lm = r["landmarks"]
    u = lambda x: (x - lm["U"]) / (lm["L"] - lm["U"])
    print(lab, "U %.1f L %.1f GU %.1f GL %.1f -> uGU %.2f uGL %.2f ref %.3g" % (lm["U"], lm["L"], lm["GU"], lm["GL"], u(lm["GU"]), u(lm["GL"]), r["ref"]))
