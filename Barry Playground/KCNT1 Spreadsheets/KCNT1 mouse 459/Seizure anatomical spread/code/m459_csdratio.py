import sys; sys.path.insert(0, "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad")
from m459_common import *
from scipy.ndimage import gaussian_filter1d, uniform_filter1d
Xc = sg.sosfiltfilt(sg.butter(4, 60, fs=FS, output="sos"), L, axis=1)
C = -np.diff(gaussian_filter1d(Xc, 1, axis=0), 2, axis=0); C = np.vstack([np.full((1, C.shape[1]), np.nan), C, np.full((1, C.shape[1]), np.nan)])
A = uniform_filter1d(np.abs(np.nan_to_num(C)), int(0.1 * FS), axis=1)[:, ::20]
base = np.median(A[:, :idx(840, 100)], 1, keepdims=True); Cz = A / base; Cz[[0, 63]] = np.nan
np.save(SP + "m459_cache/csd_ratio_100hz.npy", Cz.astype(np.float32)); print("csd ratio ok")
