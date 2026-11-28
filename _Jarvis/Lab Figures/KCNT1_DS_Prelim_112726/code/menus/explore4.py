import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.getcwd())
import menu_data as D
V = D.VAL
s = V[V.id.str.startswith("laminar|net_between")]
for _, row in s.iterrows():
    have = [l for l in D.LABS16 if np.isfinite(row.get(l, np.nan))]
    print(row.id, len(have), "m7" in have, "missing:", [l for l in D.LABS16 if l not in have])
s = V[V.id.str.contains("winner\|ds1$", regex=True) & V.id.str.startswith("laminar|")]
print(len(s), "laminar winner ds1 measures; m7 present in", int(np.isfinite(s["m7"]).sum()))
s2 = V[V.id.str.contains("winner\|ds2$", regex=True) & V.id.str.startswith("laminar|")]
print(len(s2), "laminar winner ds2 measures; m7 present in", int(np.isfinite(s2["m7"]).sum()))
