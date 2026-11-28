"""Look inside the Halo workflow's saved run (Root Canal workflow 6fa7fef7b7a3 v5): what per-event columns does it keep?"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
APP = os.environ.get("JAPP", "/gpfs2/scratch/sakhava1/kcnt1_prelim/app")
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402

for wid, v in (("6fa7fef7b7a3", 5), ("a7eee6a6ca9f", 4)):
    pay = A.ARTIFACTS.payload(wid, v)
    print("==", wid, v, None if pay is None else list(pay))
    if not pay:
        continue
    run = pay.get("run") or {}
    print(" run keys", list(run))
    cols = run.get("cols")
    if isinstance(cols, dict):
        for k, x in cols.items():
            print("   col", k, type(x).__name__, len(x) if hasattr(x, "__len__") else x, (x[:3] if isinstance(x, list) else ""))
    elif isinstance(cols, list):
        print("   cols list", len(cols), cols[:2])
    print(" counts", run.get("counts"))
    print(" halo", {k: (run.get("halo") or {}).get(k) for k in ("reach", "margin", "captured", "from_version")})
    print(" target", run.get("target"))
    print(" borders", run.get("borders"))
