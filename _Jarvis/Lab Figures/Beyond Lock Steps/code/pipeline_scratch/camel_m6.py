"""m6 s4's top hump: two sub-sinks (about 35 and 40) with a dip at 38.
Per event: both sub-sinks' strength, the dip, and how the share between
them is distributed -- one population with a camel in every event (a
fixed artefact or two layers always active together), or two populations
(each event mostly one sub-sink: the DS1/DS2 difference itself)."""
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
from backend import dspca  # noqa: E402
import numpy as np  # noqa: E402

label = sys.argv[1] if len(sys.argv) > 1 else "m6 s4"
up = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "33-37").split("-")]
lo_ = [int(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "39-42").split("-")]
VERSION = int(sys.argv[4]) if len(sys.argv) > 4 else 4
room = A._er_rooms().get("dentate_spike")
pay = A.ARTIFACTS.payload(room["id"], VERSION)
rec = next(r for r in pay["recordings"] if label in r["session_label"])
got = A._dspca_load(rec["gid"], rec["read"])
nums = [int(n) for n in got["nums"]]
p = A._er_fit_params(got, rec["box"])
res = dspca.fit(got, p, layers=A._dspca_layers(rec["gid"]))
disp = np.asarray(res["disp"], dtype=float)
T = disp.shape[2]
t = np.linspace(-50, 50, T)
win = np.abs(t) <= 3
prof = disp[:, :, win].mean(axis=2)            # E x C
neg = np.clip(-prof, 0, None)
ix = {n: i for i, n in enumerate(nums)}
U = neg[:, ix[up[0]]:ix[up[1]] + 1].max(axis=1)
L = neg[:, ix[lo_[0]]:ix[lo_[1]] + 1].max(axis=1)
share = U / np.maximum(U + L, 1e-12)
print(rec["session_label"], "n", len(U), "band", rec["box"]["sel_lo"], rec["box"]["sel_hi"])
print("upper sub-sink %s, lower %s" % (up, lo_))
print("share of the upper sub-sink, U/(U+L): deciles",
      np.round(np.percentile(share, [5, 10, 25, 50, 75, 90, 95]), 2))
h, e = np.histogram(share, bins=20, range=(0, 1))
for k in range(20):
    print("  %.2f-%.2f %s %d" % (e[k], e[k + 1], "#" * h[k], h[k]))
# Bimodality: Sarle's coefficient and a 1- vs 2-component GMM.
from scipy.stats import skew, kurtosis  # noqa: E402
bc = (skew(share) ** 2 + 1) / (kurtosis(share) + 3 * (len(share) - 1) ** 2 / ((len(share) - 2) * (len(share) - 3)))
print("bimodality coefficient %.3f (above 0.555 suggests two modes)" % bc)
try:
    from sklearn.mixture import GaussianMixture
    X = share.reshape(-1, 1)
    b1 = GaussianMixture(1, random_state=0).fit(X).bic(X)
    g2 = GaussianMixture(2, random_state=0, n_init=5).fit(X)
    b2 = g2.bic(X)
    print("dBIC (1 minus 2 components) %.1f; means %s weights %s" % (
        b1 - b2, np.round(g2.means_.ravel(), 2), np.round(g2.weights_, 2)))
except Exception as exc:  # noqa: BLE001
    print("no GMM:", exc)
# How the room's own classes (the Bite line's, as stored) sit on the share.
types = None
try:
    Ar, _r, _f = A._er_split_arrays(dict(rec, direct=True))
    types = np.asarray(Ar.get("types_bite"))
except Exception as exc:  # noqa: BLE001
    print("no arrays:", exc)
if types is not None and types.size == share.size:
    for c in (1, 2):
        s = share[types == c]
        print("Bite class %d: n %d, share median %.2f, IQR %.2f-%.2f" % (
            c, s.size, np.median(s), np.percentile(s, 25), np.percentile(s, 75)))
# Each event's dip between them, as a share of its weaker sub-sink.
d0 = ix[up[1]] + 1
dip = neg[:, d0:ix[lo_[0]]].min(axis=1) if ix[lo_[0]] > d0 else np.zeros(len(U))
print("dip / weaker sub-sink: median %.2f; events whose dip reaches zero (two separate bumps): %d of %d" % (
    float(np.median(dip / np.maximum(np.minimum(U, L), 1e-12))), int((dip <= 0).sum()), len(U)))
# The time course: do the two sub-sinks peak at the same moment?
tu = disp[:, ix[up[0]]:ix[up[1]] + 1, :].min(axis=1).mean(axis=0)
tl = disp[:, ix[lo_[0]]:ix[lo_[1]] + 1, :].min(axis=1).mean(axis=0)
print("mean sub-sink trough time: upper %.0f ms, lower %.0f ms" % (t[np.argmin(tu)], t[np.argmin(tl)]))
