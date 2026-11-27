"""Check: where the undecided events of the Strict workflow sit, per mouse (amplitude, half-width, fast power)."""
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jpages as J  # noqa: E402
import menu_data as D  # noqa: E402

rc = D.rc()
print(list(rc.columns))
s = rc[rc.wf == "strict"]
hwc = [c for c in s.columns if "hw" in c.lower() or "half" in c.lower() or "width" in c.lower()]
print("half-width columns:", hwc)
for l in J.ORDER:
    e = s[s.lab == l]
    ds = e[e.cls == "ds"]
    nb = e[e.cls == "neither"]
    bo = e[e.cls == "both"]
    und = e[e.cls.isin(["both", "neither"])]
    row = "%-4s DS n %3d amp %5.0f hf %5.1f" % (l, len(ds), ds.amp.median(), ds.hf.median())
    for c in hwc:
        row += " %s %.2f" % (c, ds[c].median())
    row += " | neither n %3d amp %5.0f hf %5.1f" % (len(nb), nb.amp.median() if len(nb) else np.nan, nb.hf.median() if len(nb) else np.nan)
    for c in hwc:
        row += " %s %.2f" % (c, nb[c].median() if len(nb) else np.nan)
    row += " | both n %3d hf %5.1f | und hf %.1f" % (len(bo), bo.hf.median() if len(bo) else np.nan, und.hf.median())
    print(row)
