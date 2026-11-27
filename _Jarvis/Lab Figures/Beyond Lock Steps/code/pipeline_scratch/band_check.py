"""Where would 'the edges of the two bottom sinks' put the band, against the
box the user drew in X-ray for the same read?"""
import glob
import sys

import numpy as np

sys.path.insert(0, r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app")
from backend import sinkcut  # noqa: E402

for f in sorted(glob.glob(r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app\GUI_logs\.cache\extraction\*.npz")):
    z = np.load(f)
    disp = z["disp"].astype(float)
    na = [int(n) for n in z["nums_all"]]
    ns = [int(n) for n in z["nums_sel"]]
    prof = np.nanmean(disp[:, :, 47:54], axis=(0, 2))       # +-3 ms at the stamp
    neg = np.clip(-prof, 0, None)
    bb = sinkcut.bumps(neg)
    big = max((b[2] for b in bb), default=0)
    keep = [b for b in bb if b[2] >= 0.15 * big]
    bottom = sorted(keep, key=lambda b: b[0])[-2:]
    desc = " ".join("%d-%d(%.0f%%)" % (na[a], na[b - 1], 100 * s / big) for a, b, s in sorted(bb, key=lambda b: b[0]) if s >= 0.05 * big)
    band = (na[bottom[0][0]], na[bottom[-1][1] - 1]) if bottom else None
    print(f.split("\\")[-1][:28], "drawn", (ns[0], ns[-1]), "auto", band, "| bumps", desc,
          "| nums_all", na[:3], "...", na[-2:])
