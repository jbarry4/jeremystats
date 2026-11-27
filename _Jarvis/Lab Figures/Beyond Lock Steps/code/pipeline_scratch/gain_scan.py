"""Every recording of a room version: each contact's gain against a 4-point
(cubic) prediction from two neighbours a side, in the baseline (|t| > 30 ms),
by quarter of the recording (drift). Lists the contacts that stand out:
more than 1.5% off and more than 5 MADs from the recording's median, or a
quarter-to-quarter swing over 1.5% (drift). Writes gain_scan.json."""
import json
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gain_scan.json")
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
import numpy as np  # noqa: E402

VERSION = int(sys.argv[1]) if len(sys.argv) > 1 else 4
room = A._er_rooms().get("dentate_spike")
pay = A.ARTIFACTS.payload(room["id"], VERSION)


def slope(y, x):
    x = x - x.mean()
    y = y - y.mean()
    d = float((x * x).sum())
    return float((x * y).sum() / d) if d > 0 else float("nan")


rows = []
for rec in pay["recordings"]:
    got = A._dspca_load(rec["gid"], rec["read"])
    nums = [int(n) for n in got["nums"]]
    bad = {int(k) for k in (got.get("bad") or {})}
    sur = np.asarray(got["sur"]["band"], dtype=float)
    E, C, T = sur.shape
    t = np.linspace(-50, 50, T)
    base = np.abs(t) > 30
    order = np.argsort([float(r.get("stamp_s") or 0) for r in got["rows"]])
    g = {}
    for c in range(2, C - 2):
        if any(nums[k] in bad for k in range(c - 2, c + 3)):
            continue
        pred = (-sur[:, c - 2] + 4 * sur[:, c - 1] + 4 * sur[:, c + 1] - sur[:, c + 2]) / 6.0
        whole = slope(sur[:, c][:, base].ravel(), pred[:, base].ravel())
        qs = ([slope(sur[b][:, c][:, base].ravel(), pred[b][:, base].ravel())
               for b in np.array_split(order, 4)] if E >= 8 else [whole])
        g[nums[c]] = (whole, qs)
    vals = np.array([v[0] for v in g.values()])
    med = float(np.median(vals))
    mad = float(np.median(np.abs(vals - med))) or 1e-4
    band = (int(rec["box"]["sel_lo"]), int(rec["box"]["sel_hi"]))
    odd = []
    for n, (w, qs) in sorted(g.items()):
        off = w - med
        swing = max(qs) - min(qs)
        if (abs(off) > 0.015 and abs(off) > 5 * mad) or swing > 0.015:
            odd.append({"num": n, "gain": round(w, 4), "off_pct": round(100 * off, 2),
                        "mads": round(off / mad, 1), "swing_pct": round(100 * swing, 2),
                        "in_band": band[0] - 2 <= n <= band[1] + 2,
                        "quarters": [round(q, 4) for q in qs]})
    rows.append({"label": rec["session_label"], "gid": rec["gid"], "band": band, "bad": sorted(bad),
                 "mad_pct": round(100 * mad, 3), "odd": odd})
    print("%-22s band %s marked bad %s | gain MAD %.2f%%" % (rec["session_label"][:22], band, sorted(bad), 100 * mad))
    for o in odd:
        print("     %s contact %2d  gain %.4f (%+.2f%%, %+.1f MAD)  quarters %s%s" % (
            "IN " if o["in_band"] else "   ", o["num"], o["gain"], o["off_pct"], o["mads"],
            " ".join("%.3f" % q for q in o["quarters"]),
            ("  drift %.1f%%" % o["swing_pct"]) if o["swing_pct"] > 1.5 else ""))
    sys.stdout.flush()
with open(OUT, "w") as fh:
    json.dump(rows, fh)
