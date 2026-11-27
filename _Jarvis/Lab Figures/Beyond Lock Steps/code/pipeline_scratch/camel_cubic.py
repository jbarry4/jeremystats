"""Where the camel dips sit with the bad contacts repaired linearly (as read)
and cubically: do the dips at repaired contacts go away?"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
from backend import dspca  # noqa: E402
import numpy as np  # noqa: E402

room = A._er_rooms().get("dentate_spike")
pay = A.ARTIFACTS.payload(room["id"], 4)


def cubic(got):
    nums = [int(n) for n in got["nums"]]
    bad = {int(k) for k in (got.get("bad") or {})}
    out = dict(got)
    out["sur"] = {}
    for key, X in got["sur"].items():
        X = np.array(X, dtype=float, copy=True)
        for b in sorted(bad):
            i = nums.index(b)
            nb = [i - 2, i - 1, i + 1, i + 2]
            if all(0 <= k < len(nums) and nums[k] not in bad for k in nb):
                X[:, i] = (-X[:, i - 2] + 4 * X[:, i - 1] + 4 * X[:, i + 1] - X[:, i + 2]) / 6.0
        out["sur"][key] = X
    return out


def dips(res, nums, band, rel=0.8):
    disp = np.asarray(res["disp"], dtype=float)
    t = np.linspace(-50, 50, disp.shape[2])
    sel = [i for i, n in enumerate(nums) if band[0] <= n <= band[1]]
    neg = np.clip(-disp[:, sel][:, :, np.abs(t) <= 3].mean(axis=2), 0, None)
    h = {}
    for row in neg:
        for j in range(1, len(sel) - 1):
            if row[j] < row[j - 1] and row[j] <= row[j + 1]:
                left, right = row[:j].max(), row[j + 1:].max()
                if row[j] < rel * min(left, right):
                    n = nums[sel[j]]
                    h[n] = h.get(n, 0) + 1
    return dict(sorted(h.items(), key=lambda kv: -kv[1])[:6])


for rec in pay["recordings"]:
    if rec["n"] < 20:
        continue
    got = A._dspca_load(rec["gid"], rec["read"])
    nums = [int(n) for n in got["nums"]]
    band = (int(rec["box"]["sel_lo"]), int(rec["box"]["sel_hi"]))
    bad = sorted(int(k) for k in got.get("bad") or {})
    inside = [b for b in bad if band[0] - 1 <= b <= band[1] + 1]
    if not inside:
        continue
    lay = A._dspca_layers(rec["gid"])
    r_l = dspca.fit(got, A._er_fit_params(got, rec["box"]), layers=lay)
    gc = cubic(got)
    r_c = dspca.fit(gc, A._er_fit_params(gc, rec["box"]), layers=lay)
    print("%-22s band %s repaired inside %s\n    linear dips %s\n    cubic  dips %s" % (
        rec["session_label"][:22], band, inside, dips(r_l, nums, band), dips(r_c, nums, band)))
    sys.stdout.flush()
