"""Do the off-gain contacts matter? Each recording refitted with them taken
out (made again from two good neighbours a side, cubic), and the Bite line
(humps) compared: split, SI, notched events, and the mean profile."""
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
from backend import dspca  # noqa: E402
from backend import extraction as EX  # noqa: E402
import numpy as np  # noqa: E402

FIX = {"m22 s3": [25, 49, 62], "m28 s2": [25, 49, 44, 52], "m21 s2": [25, 49, 62],
       "m7 s2": [32, 51], "m6 s4": [50], "m26 s2": [50]}
room = A._er_rooms().get("dentate_spike")
pay = A.ARTIFACTS.payload(room["id"], 4)


def recut(got, extra):
    """The read with `extra` contacts made again, cubic where two good
    neighbours a side exist, else linear."""
    nums = [int(n) for n in got["nums"]]
    bad = {int(k) for k in (got.get("bad") or {})} | set(extra)
    out = dict(got)
    out["sur"] = {}
    for key, X in got["sur"].items():
        X = np.array(X, dtype=float, copy=True)
        for b in sorted(extra):
            i = nums.index(b)
            nb = [i - 2, i - 1, i + 1, i + 2]
            if all(0 <= k < len(nums) and nums[k] not in bad for k in nb):
                X[:, i] = (-X[:, i - 2] + 4 * X[:, i - 1] + 4 * X[:, i + 1] - X[:, i + 2]) / 6.0
            else:
                lo = max(k for k in range(i) if nums[k] not in bad)
                hi = min(k for k in range(i + 1, len(nums)) if nums[k] not in bad)
                w = (i - lo) / float(hi - lo)
                X[:, i] = (1 - w) * X[:, lo] + w * X[:, hi]
        out["sur"][key] = X
    return out


for lab, extra in FIX.items():
    rec = next(r for r in pay["recordings"] if lab in r["session_label"])
    got = A._dspca_load(rec["gid"], rec["read"])
    lay = A._dspca_layers(rec["gid"])
    print("%s band %s-%s, taking out %s" % (rec["session_label"], rec["box"]["sel_lo"], rec["box"]["sel_hi"], extra))
    for name, g in (("as read", got), ("taken out", recut(got, extra))):
        p = A._er_fit_params(g, rec["box"])
        res = dspca.fit(g, p, layers=lay)
        Ar = EX.split_arrays(res)
        EX.add_bite(Ar, str(p.rule), bool(p.flip))
        v = EX.bite_view(Ar)
        disp = np.asarray(res["disp"], dtype=float)
        t = np.linspace(-50, 50, disp.shape[2])
        nums = [int(n) for n in g["nums"]]
        mp = disp[:, :, np.abs(t) <= 3].mean(axis=(0, 2))
        lo, hi = int(rec["box"]["sel_lo"]), int(rec["box"]["sel_hi"])
        prof = " ".join("%d:%+.2f" % (n, mp[nums.index(n)]) for n in range(lo, hi + 1))
        print("   %-9s split %s/%s SI %s (%s) | humps part at %s, notched %s | pca SI %s delta SI %s" % (
            name, v["scores"]["n1"], v["scores"]["n2"], v["scores"]["si"], v["verdict"]["word"],
            v["bumps"]["hump_at"], v["bumps"]["camel"],
            A._er_overlap_scores(Ar, Ar["types_pca"])["si"] if A._er_overlap_scores(Ar, Ar["types_pca"]) else None,
            A._er_overlap_scores(Ar, Ar["types_delta"])["si"] if A._er_overlap_scores(Ar, Ar["types_delta"]) else None))
        print("      mean CSD at the stamp:", prof)
    sys.stdout.flush()
