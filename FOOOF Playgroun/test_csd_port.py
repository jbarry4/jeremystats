"""Check ds_pca's StandardCSD against the arithmetic in Toothy's icsd.py.

Toothy's icsd.py cannot be imported here (it needs `quantities`, which is not
installed), so the check is against the source read line by line plus two
analytic cases the method has a known answer for.
"""
import os
import sys

import numpy as np
from scipy.signal import convolve
from scipy.signal.windows import gaussian

sys.path.insert(0, r"C:\Users\Z390\Desktop\jeremystats\FOOOF Playgroun")
import ds_pca  # noqa: E402

FAIL = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAIL.append(name)


# --- 1. the f_inv matrix, built the way icsd.py:222-231 builds it ---------
# f_inv = -eye(n); inner rows [1,-2,1]; whole thing * -sigma/h
def toothy_f_inv(n, sigma, h):
    f = -np.eye(n)
    for j in range(1, n - 1):
        f[j, j - 1:j + 2] = np.array([1.0, -2.0, 1.0])
    return f * -sigma / h


rng = np.random.default_rng(7)
n_ch, n_col = 12, 5
lfp = rng.normal(size=(n_ch, n_col))
sigma, h = 0.3, 30e-6

# icsd.py:207-215 (vaknin) then :243 (dot, then [1:-1])
ext = np.empty((n_ch + 2, n_col))
ext[0] = lfp[0]
ext[1:-1] = lfp
ext[-1] = lfp[-1]
ref = toothy_f_inv(n_ch + 2, sigma, h).dot(ext)[1:-1]

mine = ds_pca.standard_csd(lfp, h, sigma=sigma, vaknin=True, h_power=1)
check("StandardCSD + Vaknin matches icsd.py line for line",
      np.allclose(ref, mine, rtol=0, atol=1e-12),
      "max |diff| = %.3e" % np.abs(ref - mine).max())
check("output has one row per contact",
      mine.shape == (n_ch, n_col), str(mine.shape))

# --- 2. the analytic case: a quadratic potential has a constant CSD -------
# phi(z) = z^2  ->  d2phi/dz2 = 2  ->  csd = -sigma * 2 (per h_power=2)
z = np.arange(n_ch) * h
phi = (z ** 2)[:, None]
csd2 = ds_pca.standard_csd(phi, h, sigma=sigma, vaknin=False, h_power=2)
inner = csd2[1:-1, 0]
check("quadratic potential -> constant CSD in the interior",
      np.allclose(inner, inner[0], rtol=1e-6),
      "value %.6g, expected %.6g" % (inner[0], -sigma * 2.0))
check("that constant is -sigma * d2phi/dz2",
      np.isclose(inner[0], -sigma * 2.0, rtol=1e-6))

# --- 3. the spatial filter kernel, icsd.py:136-138, :160-163 -------------
num = gaussian(3, 1.0)
num = num / num.sum()
check("gaussian(3, 1) normalized is the [.274 .452 .274] kernel",
      np.allclose(num, [0.27406862, 0.45186276, 0.27406862], atol=1e-7),
      np.array2string(num, precision=6))

x = rng.normal(size=(n_ch, n_col))
ref_f = np.array(x, copy=True)
for i in range(n_col):
    ref_f[:, i] = convolve(ref_f[:, i], num, "same")
check("filter_csd matches a per-column 'same' convolution",
      np.allclose(ref_f, ds_pca.filter_csd(x, 3, 1.0), atol=1e-12))

# --- 4. pyfx.Normalize, per column ---------------------------------------
y = np.array([[1.0, 5.0], [3.0, 5.0], [5.0, 5.0]])
nrm = ds_pca.normalize_columns(y)
check("min-max normalize per event (column)",
      np.allclose(nrm[:, 0], [0.0, 0.5, 1.0]))
check("a flat column comes back as zeros, not NaN (pyfx.Normalize)",
      np.allclose(nrm[:, 1], 0.0))

# --- 5. the features are invariant to units, so mV vs uV cannot matter ----
a = ds_pca.normalize_columns(ds_pca.filter_csd(
    ds_pca.standard_csd(lfp, h, sigma=sigma), 3, 1.0))
b = ds_pca.normalize_columns(ds_pca.filter_csd(
    ds_pca.standard_csd(lfp * 1000.0, h, sigma=sigma), 3, 1.0))
check("normalized features are scale-invariant (uV vs mV is irrelevant)",
      np.allclose(a, b, atol=1e-12))

print("")
print("%d checks, %d failed" % (8, len(FAIL)))
sys.exit(1 if FAIL else 0)
