import sys; sys.path.insert(0, "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad")
from m459_common import *
from scipy.ndimage import gaussian_filter1d
def xc(a, b, maxlag=0.03):
    a = a - a.mean(); b = b - b.mean(); n = int(maxlag * FS)
    cc = np.array([np.dot(a[max(0, -k):len(a) - max(0, k)], b[max(0, k):len(b) - max(0, -k)]) for k in range(-n, n + 1)])
    return np.arange(-n, n + 1) / FS * 1000, cc / np.sqrt((a**2).sum() * (b**2).sum())
t0, t1 = 897.0, 912.0
X = L[:, idx(t0):idx(t1)]
hf = sg.sosfiltfilt(sg.butter(4, [150, 600], "band", fs=FS, output="sos"), X, axis=1)
env = gaussian_filter1d(np.abs(hf), 0.002 * FS, axis=1)
h = env[39:49].mean(0); c1 = env[4:9].mean(0)
lags, cc = xc(h, c1)
pk = sg.find_peaks(cc)[0]
print("HF envelope xcorr hilus->CA1pyr: local peaks (lag ms, r):", [(round(lags[i], 1), round(cc[i], 2)) for i in pk])
la, ac = xc(h, h, 0.04); pa = sg.find_peaks(ac)[0]
print("hilus HF envelope autocorr peaks (ms):", [(round(la[i], 1), round(ac[i], 2)) for i in pa if la[i] > 0][:4])
# CSD sink-to-sink: supra ML (29-33) vs CA1 radiatum (12-22), low-passed
lf = sg.sosfiltfilt(sg.butter(4, [1, 300], "band", fs=FS, output="sos"), X, axis=1)
C = -np.diff(gaussian_filter1d(lf, 1, axis=0), 2, axis=0); C = np.vstack([C[:1]*0, C, C[:1]*0])
ml = -C[28:33].mean(0); rad = -C[11:22].mean(0); gcl = -C[34:39].mean(0); slm = -C[22:27].mean(0)
for nm, y in [("CA1 rad sink", rad), ("CA1 l-m sink", slm), ("supra GCL", gcl)]:
    l_, c_ = xc(ml, y); p_ = sg.find_peaks(c_)[0]
    print(f"supraML sink -> {nm}: peaks", [(round(l_[i], 1), round(c_[i], 2)) for i in p_ if abs(l_[i]) <= 20])
