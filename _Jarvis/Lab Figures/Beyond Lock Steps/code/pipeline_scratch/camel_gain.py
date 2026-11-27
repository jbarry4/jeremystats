"""Is a contact's gain off? Each contact predicted from two neighbours on each
side (4-point cubic: exact for any field smooth to third order, so a real
sink does not look like a gain error the way it does against 2 neighbours),
the slope of the measured on the predicted in the baseline (|t| > 30 ms),
and the gain change at the camel's dip that would remove the dip.
Usage: camel_gain.py <label> [dip contact] [version]"""
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
import numpy as np  # noqa: E402

label = sys.argv[1]
dipc = int(sys.argv[2]) if len(sys.argv) > 2 else None
VERSION = int(sys.argv[3]) if len(sys.argv) > 3 else 4
room = A._er_rooms().get("dentate_spike")
pay = A.ARTIFACTS.payload(room["id"], VERSION)
rec = next(r for r in pay["recordings"] if label in r["session_label"])
got = A._dspca_load(rec["gid"], rec["read"])
nums = [int(n) for n in got["nums"]]
bad = {int(k) for k in (got.get("bad") or {})}
sur = np.asarray(got["sur"]["band"], dtype=float)
E, C, T = sur.shape
t = np.linspace(-50, 50, T)
base = np.abs(t) > 30
order = np.argsort([float(r.get("stamp_s") or 0) for r in got["rows"]])


def slope(y, x):
    x = x - x.mean()
    y = y - y.mean()
    return float((x * y).sum() / (x * x).sum())


print(rec["session_label"], "bad", sorted(bad))
gains = {}
for c in range(2, C - 2):
    if any(nums[k] in bad for k in range(c - 2, c + 3)):
        continue
    pred = (-sur[:, c - 2] + 4 * sur[:, c - 1] + 4 * sur[:, c + 1] - sur[:, c + 2]) / 6.0
    g = slope(sur[:, c][:, base].ravel(), pred[:, base].ravel())
    blocks = [slope(sur[b][:, c][:, base].ravel(), pred[b][:, base].ravel()) for b in np.array_split(order, 4)]
    gains[nums[c]] = (g, blocks)
lo, hi = int(rec["box"]["sel_lo"]) - 4, int(rec["box"]["sel_hi"]) + 4
vals = np.array([v[0] for v in gains.values()])
print("cubic-predicted gain, all contacts: median %.4f, MAD %.4f" % (
    np.median(vals), np.median(np.abs(vals - np.median(vals)))))
for n in range(max(1, lo), min(64, hi) + 1):
    if n not in gains:
        print("  %2d  (bad, or within two of a bad contact)" % n)
        continue
    g, b = gains[n]
    flag = " <--" if abs(g - np.median(vals)) > 5 * max(1e-4, np.median(np.abs(vals - np.median(vals)))) else ""
    print("  %2d  gain %.4f  by quarter %s%s" % (n, g, " ".join("%.4f" % x for x in b), flag))
if dipc:
    # The mean LFP at the stamp and the gain change at dipc that would make
    # its second difference the mean of its neighbours'.
    at = np.abs(t) <= 3
    V = sur[:, :, at].mean(axis=(0, 2))
    i = nums.index(dipc)
    d2 = lambda k: V[k - 1] - 2 * V[k] + V[k + 1]  # noqa: E731
    want = 0.5 * (d2(i - 1) + d2(i + 1))
    dv = (d2(i) - want) / 2.0
    print("at the stamp: V[%d] = %.1f uV; d2 %d/%d/%d = %.2f/%.2f/%.2f uV; removing the dip needs V[%d] %+.2f uV (%.2f%% gain)" % (
        dipc, V[i], dipc - 1, dipc, dipc + 1, d2(i - 1), d2(i), d2(i + 1), dipc, dv, 100 * dv / V[i]))
    # Per event: the same, as a distribution (a gain error is one number).
    Ve = sur[:, :, at].mean(axis=2)
    d2e = lambda k: Ve[:, k - 1] - 2 * Ve[:, k] + Ve[:, k + 1]  # noqa: E731
    dve = (d2e(i) - 0.5 * (d2e(i - 1) + d2e(i + 1))) / 2.0
    ratio = dve / Ve[:, i]
    print("per event, the needed gain change: median %.2f%%, IQR %.2f%% to %.2f%%; V[%d] median %.1f uV" % (
        100 * np.median(ratio), 100 * np.percentile(ratio, 25), 100 * np.percentile(ratio, 75), dipc, np.median(Ve[:, i])))
    # And in the baseline: is the same 'dip' there, in proportion to V?
    Vb = sur[:, :, base]
    d2b = lambda k: Vb[:, k - 1] - 2 * Vb[:, k] + Vb[:, k + 1]  # noqa: E731
    exc = (d2b(i) - 0.5 * (d2b(i - 1) + d2b(i + 1))) / 2.0
    print("baseline: slope of that excess on V[%d] = %.4f (a gain error of g shows as -g... here %.2f%%)" % (
        dipc, slope(exc.ravel(), Vb[:, i].ravel()), 100 * slope(exc.ravel(), Vb[:, i].ravel())))
