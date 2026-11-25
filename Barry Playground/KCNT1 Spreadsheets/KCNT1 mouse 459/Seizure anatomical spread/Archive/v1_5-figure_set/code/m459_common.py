import numpy as np
from scipy import signal as sg
from scipy.ndimage import uniform_filter1d
SP = "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad/"
z = np.load(SP + "m459_cache/m459_s1_400_1000.npz")
L = z["lfp"].astype(np.float32); M = z["mua"].astype(np.float32); FS = 2000.0; FSM = 1000.0; T0 = 400.0
L[58] = 0.5 * (L[57] + L[59]); M[58] = 0.5 * (M[57] + M[59])
REGIONS = [  # name, first, last (CSC, inclusive), colour
 ("CA1 (or/pyr)", 1, 10, "#7b3294"),
 ("CA1 rad/l-m", 11, 27, "#c2a5cf"),
 ("Upper blade ML", 28, 34, "#1b7837"),
 ("Upper blade GCL", 35, 39, "#5aae61"),
 ("Hilus", 40, 49, "#d7301f"),
 ("Lower blade GCL", 50, 52, "#2166ac"),
 ("Lower blade ML", 53, 59, "#67a9cf"),
 ("Below DG", 60, 64, "#969696"),
]
def region_of(ch):  # ch = CSC number
    for n, a, b, c in REGIONS:
        if a <= ch <= b: return n, c
CHCOL = [region_of(i + 1)[1] for i in range(64)]
idx = lambda t, fs=FS: int(round((t - T0) * fs))
def features(win=0.25):
    lf = sg.sosfiltfilt(sg.butter(4, [1, 100], "band", fs=FS, output="sos"), L, axis=1)
    ll = uniform_filter1d(np.abs(np.diff(lf, axis=1, prepend=lf[:, :1])), int(win * FS), axis=1)[:, ::20]  # 100 Hz
    mu = uniform_filter1d(M, int(win * FSM), axis=1)[:, ::10]                                              # 100 Hz
    b = slice(idx(400, 100), idx(840, 100))
    zs = lambda X: (X - np.median(X[:, b], 1, keepdims=True)) / (1.4826 * np.median(np.abs(X[:, b] - np.median(X[:, b], 1, keepdims=True)), 1, keepdims=True))
    return zs(ll), zs(mu)
