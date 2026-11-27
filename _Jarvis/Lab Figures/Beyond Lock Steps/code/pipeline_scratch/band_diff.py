import os, sys, pickle, warnings
warnings.filterwarnings("ignore")
APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP); sys.path.insert(0, APP)
import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np
from backend.app import app
from backend import app as A
HERE = os.path.dirname(os.path.abspath(__file__))
lab = sys.argv[1]
B = pickle.load(open(os.path.join(HERE, "bandread", lab + ".pkl"), "rb"))
got = A._dspca_load(B["gid"], B["read"])
ref = np.asarray(got["sur"]["band"], float)
x = B["bands"]["ds"].astype(float)
d = np.abs(x - ref)
pk = np.abs(ref).max()
print("bad", sorted((got.get("bad") or {}).keys()))
print("per channel worst/peak:", " ".join("%d:%.3f" % (n, v) for n, v in zip(B["nums"], d.max(axis=(0, 2)) / pk) if v > 0.01))
ev = d.max(axis=(1, 2)) / pk
print("events over 2%%: %d of %d; median %.4f" % ((ev > 0.02).sum(), ev.size, np.median(ev)))
tt = d.max(axis=(0, 1)) / pk
print("by time sample (first, mid, last):", tt[:3], tt[48:53], tt[-3:])
rows = got["rows"]
i = int(ev.argmax())
print("worst event", i, rows[i])
st = np.array([r["stamp_s"] for r in rows])
print("gap to neighbours (s):", np.diff(st)[max(0, i - 2):i + 2])
