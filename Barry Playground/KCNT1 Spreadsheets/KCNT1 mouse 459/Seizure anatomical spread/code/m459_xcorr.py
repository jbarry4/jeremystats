import sys; sys.path.insert(0, "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad")
from m459_common import *
from scipy.ndimage import gaussian_filter1d
def env(t0, t1, band=(150, 600)):
    X = L[:, idx(t0):idx(t1)]
    hf = sg.sosfiltfilt(sg.butter(4, band, "band", fs=FS, output="sos"), X, axis=1)
    return gaussian_filter1d(np.abs(hf), 0.002 * FS, axis=1)
G = {"Upper ML": (28, 34), "Upper GCL": (35, 39), "Hilus": (40, 49), "Lower GCL": (50, 52), "CA1 pyr": (5, 9)}
def xl(a, b, maxlag=0.03):
    a = a - a.mean(); b = b - b.mean(); n = int(maxlag * FS)
    cc = np.array([np.dot(a[max(0, -k):len(a) - max(0, k)], b[max(0, k):len(b) - max(0, -k)]) for k in range(-n, n + 1)])
    cc /= np.sqrt((a ** 2).sum() * (b ** 2).sum()); k = np.argmax(cc)
    return (k - n) / FS * 1000, cc[k]
print("lag of X relative to Hilus HF envelope (positive = X later), and peak r")
for t0, t1 in [(889.0, 892.0), (892.0, 897.0), (897.0, 902.0), (902.0, 907.0), (907.0, 912.0), (912.0, 916.5)]:
    E = env(t0, t1); ref = E[39:49].mean(0)
    out = []
    for n, (a, b) in G.items():
        if n == "Hilus": continue
        lag, r = xl(ref, E[a-1:b].mean(0)); out.append(f"{n} {lag:+5.1f}ms r={r:.2f}")
    print(f"{t0}-{t1}: " + " | ".join(out))
