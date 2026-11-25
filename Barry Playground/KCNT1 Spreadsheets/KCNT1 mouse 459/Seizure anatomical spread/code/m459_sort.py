import numpy as np
from scipy import signal as sg
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture
SP = "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad/"
z = np.load(SP + "m459_cache/m459_s1_hilar_hp.npz")
H = z["hp"]; CH = z["chans"]; FS = float(z["fs"]); T0 = float(z["t0"]); SC = float(z["scale_uV"])
nC, nS = H.shape
mad = np.median(np.abs(H[:, :int(400 * FS)].astype(np.float32)), 1) / 0.6745
thr = -5.0 * mad
# detect negative peaks per channel
evs = []
for c in range(nC):
    x = H[c].astype(np.float32)
    pk, pr = sg.find_peaks(-x, height=-thr[c], distance=int(0.0008 * FS))
    evs.append(np.c_[pk, np.full(len(pk), c), x[pk]])
E = np.vstack(evs); E = E[np.argsort(E[:, 0])]
# dedupe: within 0.4 ms keep the most negative (relative to its channel MAD)
keep = []; win = int(0.0004 * FS); i = 0
rel = E[:, 2] / mad[E[:, 1].astype(int)]
while i < len(E):
    j = i
    while j + 1 < len(E) and E[j + 1, 0] - E[i, 0] <= win: j += 1
    k = i + np.argmin(rel[i:j + 1]); keep.append(k); i = j + 1
E = E[keep]
t = E[:, 0].astype(int); pc = E[:, 1].astype(int)
pre, post = int(0.0006 * FS), int(0.0012 * FS)
ok = (t > pre) & (t < nS - post) & (pc >= 3) & (pc <= nC - 4)
t, pc = t[ok], pc[ok]
print("spikes:", len(t))
def wf(ti, ci): return np.stack([H[ci + d, ti - pre:ti + post] for d in range(-3, 4)]).astype(np.float32) * SC
W = np.stack([wf(a, b) for a, b in zip(t, pc)])            # n x 7 x 54
tsec = T0 + t / FS
base = tsec < 886
# features: PCA on 7-ch waveform + peak channel position
F = W.reshape(len(W), -1)
pca = PCA(8).fit(F[base][::2]); P = pca.transform(F)
X = np.c_[P, pc * 40.0]
best = None
rng = np.random.default_rng(0); sub = rng.choice(np.flatnonzero(base), min(60000, base.sum()), replace=False)
for k in range(4, 15):
    g = GaussianMixture(k, covariance_type="full", random_state=0).fit(X[sub]); b = g.bic(X[sub])
    if best is None or b < best[0]: best = (b, k, g)
_, K, gmm = best; print("K =", K)
lab = gmm.predict(X); post_p = gmm.predict_proba(X).max(1)
lab[post_p < 0.8] = -1
units = []
for u in range(K):
    m = (lab == u) & base
    if m.sum() < 200: continue
    T = W[(lab == u) & base].mean(0); main = np.argmin(T.min(1)); w = T[main]
    up = sg.resample(w, len(w) * 8); tr = np.argmin(up); pk_ = tr + np.argmax(up[tr:tr + int(0.0012 * FS * 8)])
    width = (pk_ - tr) / (FS * 8) * 1000
    st = np.sort(tsec[(lab == u) & base]); isi = np.diff(st)
    rate = m.sum() / (886 - T0)
    chan = CH[int(np.median(pc[lab == u])) + main - 3]
    units.append(dict(u=u, n=int(m.sum()), rate=rate, width=width, amp=float(-w.min()), chan=int(chan), isiv=float((isi < 0.0015).mean() * 100)))
units.sort(key=lambda d: d["chan"])
print(" u   chan  rate(Hz)  width(ms)  amp(uV)  ISI<1.5ms%  n")
for d in units: print(f"{d['u']:2d}  {d['chan']:4d}  {d['rate']:7.2f}  {d['width']:8.2f}  {d['amp']:7.0f}  {d['isiv']:9.2f}  {d['n']}")
np.savez(SP + "m459_cache/hilar_sort.npz", tsec=tsec, lab=lab, pc=pc, units=np.array([[d[k] for k in ("u", "chan", "rate", "width", "amp", "isiv", "n")] for d in units]),
         templates=np.stack([W[(lab == d["u"]) & base][:3000].mean(0) for d in units]))
