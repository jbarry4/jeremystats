"""
csc.py -- Session loading + signal conditioning for the CSC viewer.

Handles both ends of the lab CSC chain:
  RAW       a folder of CSC*.ncs  (Neuralynx, read by nlx.py)
  CONVERTED a .mat written by CSC2LL_uV_mex_disk.m, holding
              d   [nCh x nSamp] microvolts, NaN-padded
              sfx sampling rate
              badch / chan_labels / kept_channels / units

Everything is returned in microvolts so the two paths are interchangeable.

Windowed reads are decimated to a min/max envelope: for a target pixel width
the viewer gets 2 points per pixel that preserve the true signal extremes, so
spikes never vanish at zoomed-out scales the way naive subsampling loses them.
"""
from __future__ import annotations

import os
import warnings
import numpy as np

from . import demo, nlx

try:
    from scipy.signal import butter, sosfiltfilt, iirnotch, tf2sos
    HAVE_SCIPY = True
except Exception:                                    # pragma: no cover
    HAVE_SCIPY = False

_MAT_CACHE = {}


# --------------------------------------------------------------------------
# Session discovery
# --------------------------------------------------------------------------
def describe_path(path):
    """Classify a dropped/selected path as a CSC session, .mat, or .ncs file."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return {"ok": False, "error": "Path not found: " + path}

    if os.path.isdir(path):
        ncs_all = nlx.list_csc_files(path, even_only=False)
        mats = [f for f in sorted(os.listdir(path)) if f.lower().endswith(".mat")]
        if ncs_all:
            return {"ok": True, "kind": "ncs_folder", "path": path,
                    "n_ncs": len(ncs_all), "mats": mats}
        if mats:
            return {"ok": True, "kind": "mat_folder", "path": path, "mats": mats}
        return {"ok": False, "error": "No CSC*.ncs or .mat files in that folder."}

    ext = os.path.splitext(path)[1].lower()
    if ext == ".ncs":
        return {"ok": True, "kind": "ncs_file", "path": path}
    if ext == ".mat":
        return {"ok": True, "kind": "mat_file", "path": path}
    return {"ok": False, "error": "Unsupported file type: " + ext}


def open_session(path, even_only=None, invert=True):
    """Open a session and return its channel inventory + timing metadata.

    A "demo:" path is a recording that is not on disk -- see demo.py. It
    exists so the Guide works on a laptop with nothing mounted, and it goes
    through the same code as everything else from here on.

    `even_only=None` means "work it out", which is the default because
    neither answer is right for both rigs. See nlx.channel_scheme: the old
    32-channel probe left its odd AD channels empty, the 64-channel probe
    fills all of them, and assuming either one silently halves or doubles
    what anybody looks at. True or False still forces it.
    """
    if demo.is_demo(path):
        return demo.open_session(path, even_only, invert)

    info = describe_path(path)
    if not info.get("ok"):
        return info

    kind = info["kind"]
    if kind == "ncs_folder":
        return _open_ncs_folder(info["path"], even_only, invert)
    if kind == "ncs_file":
        folder = os.path.dirname(info["path"])
        sess = _open_ncs_folder(folder, even_only, invert)
        if sess.get("ok"):
            return sess
        return _open_single_ncs(info["path"], invert)
    if kind == "mat_file":
        return _open_mat(info["path"])
    if kind == "mat_folder":
        # Pipeline_Main.m ignores ets.mat when auto-detecting the data file.
        cands = [m for m in info["mats"] if not m.lower().startswith("ets")]
        if not cands:
            return {"ok": False, "error": "Only ets.mat found -- no CSC data .mat."}
        return _open_mat(os.path.join(info["path"], cands[0]))
    return {"ok": False, "error": "Unrecognized session type."}


def _open_ncs_folder(folder, even_only, invert):
    scheme = None
    if even_only is None:
        scheme = nlx.channel_scheme(folder)
        even_only = (scheme["scheme"] == "even")
    files = nlx.list_csc_files(folder, even_only=even_only)
    if not files:
        files = nlx.list_csc_files(folder, even_only=False)
        even_only = False
    if not files:
        return {"ok": False, "error": "No CSC*.ncs in " + folder}

    hdr = nlx.read_header(files[0][1])
    fs = nlx._header_float(hdr, "SamplingFrequency") or nlx.DEFAULT_FS
    adbv = nlx._header_float(hdr, "ADBitVolts") or nlx.FALLBACK_ADBITVOLTS

    size = os.path.getsize(files[0][1])
    n_rec = max(0, (size - nlx.HEADER_BYTES) // nlx.RECORD_DTYPE.itemsize)
    duration = n_rec * nlx.SAMPLES_PER_RECORD / fs if fs else 0.0

    # A file with a header and no data is not a recording.
    #
    # An aborted acquisition leaves CSC*.ncs files of exactly 16384 bytes, and
    # a zero-byte placeholder does the same thing. Those used to open
    # perfectly happily with duration 0.0 -- and then every panel, every pan
    # and every poll failed with "No samples in 0.000-4.000 s", four times a
    # refresh, for as long as the session stayed open. That is the error spam:
    # one bad folder, hundreds of failures, none of which says what is
    # actually wrong.
    #
    # Refusing here means one clear message instead.
    if n_rec <= 0:
        empties = sum(
            1 for _num, fp in files
            if os.path.getsize(fp) <= nlx.HEADER_BYTES)
        return {
            "ok": False,
            "error": (
                "That folder has %d CSC file(s) but no data in them -- %d of "
                "them are header-only or empty. It looks like an acquisition "
                "that was started and stopped, or a partial copy. There is "
                "nothing to plot."
                % (len(files), empties)),
            "path": folder,
            "empty": True,
            "n_csc_files": len(files),
        }

    channels = []
    for i, (num, p) in enumerate(files):
        channels.append({"index": i, "number": num, "label": "CSC" + str(num),
                         "file": p, "bad": False})

    return {
        "ok": True, "source": "ncs", "path": folder,
        "name": os.path.basename(folder.rstrip("\\/")) or folder,
        "fs": float(fs), "adbitvolts": float(adbv), "duration_s": float(duration),
        "even_only": bool(even_only), "invert": bool(invert),
        # How the channel list was arrived at, so it is visible rather than
        # assumed. `decided` is None when the caller forced it.
        "channel_scheme": scheme,
        "n_csc_files": len(nlx.list_csc_files(folder, even_only=False)),
        "channels": channels, "units": "microvolts",
    }


def _open_single_ncs(path, invert):
    # Header plus file size only. read_ncs() would decode every sample in the
    # file just to report its length, which on a 40-minute recording is a
    # few hundred megabytes of work for four numbers -- and the window reader
    # seeks to what it needs anyway.
    hdr = nlx.read_header(path)
    fs = nlx._header_float(hdr, "SamplingFrequency") or nlx.DEFAULT_FS
    adbv = nlx._header_float(hdr, "ADBitVolts") or nlx.FALLBACK_ADBITVOLTS
    size = os.path.getsize(path)
    n_rec = max(0, (size - nlx.HEADER_BYTES) // nlx.RECORD_DTYPE.itemsize)
    duration = n_rec * nlx.SAMPLES_PER_RECORD / fs if fs else 0.0

    m = nlx._CSC_NAME_RE.match(os.path.basename(path))
    num = int(m.group(1)) if m else 0
    return {
        "ok": True, "source": "ncs", "path": os.path.dirname(path),
        "name": os.path.basename(path),
        "fs": float(fs), "adbitvolts": float(adbv),
        "duration_s": float(duration), "even_only": False, "invert": invert,
        "channels": [{"index": 0, "number": num, "label": os.path.basename(path),
                      "file": path, "bad": False}],
        "units": "microvolts",
    }


def _load_mat(path):
    """Load a CSC .mat (v7 via scipy, v7.3 via h5py) and normalize its fields."""
    key = path + ":" + str(os.path.getmtime(path))
    if key in _MAT_CACHE:
        return _MAT_CACHE[key]

    payload = None
    try:                                     # v7 / v6
        import scipy.io as sio
        raw = sio.loadmat(path, squeeze_me=True, struct_as_record=False)
        payload = _normalize_mat_v7(raw)
    except Exception:
        payload = None

    if payload is None:                      # v7.3 (HDF5)
        import h5py
        fh = h5py.File(path, "r")
        payload = _normalize_mat_v73(fh)

    _MAT_CACHE.clear()                       # one session resident at a time
    _MAT_CACHE[key] = payload
    return payload


def _pick_matrix(cands):
    """Choose the [nCh x nSamp] signal matrix from a bag of variables."""
    if "d" in cands:
        return "d", cands["d"]
    best, best_size = None, -1
    for name, arr in cands.items():
        if getattr(arr, "ndim", 0) == 2 and min(arr.shape) >= 1:
            size = arr.shape[0] * arr.shape[1]
            if size > best_size:
                best, best_size = name, size
    return (best, cands[best]) if best is not None else (None, None)


def _normalize_mat_v7(raw):
    arrays = {}
    for k, v in raw.items():
        if not k.startswith("__") and hasattr(v, "shape") and getattr(v, "ndim", 0) == 2:
            arrays[k] = v
    name, mat = _pick_matrix(arrays)
    if mat is None:
        raise ValueError("No 2-D data matrix found in .mat")
    mat = np.asarray(mat)
    if mat.shape[0] > mat.shape[1]:          # stored [nSamp x nCh]
        mat = mat.T
    fs = _scalar(raw.get("sfx")) or _scalar(raw.get("fs")) or nlx.DEFAULT_FS
    return {
        "data": mat, "fs": float(fs), "var": name,
        "labels": _str_list(raw.get("chan_labels"), mat.shape[0]),
        "kept": _num_list(raw.get("kept_channels"), mat.shape[0]),
        "badch": _bool_list(raw.get("badch")),
        "handle": None,
    }


def _normalize_mat_v73(fh):
    import h5py
    arrays = {}
    for k in fh.keys():
        if k.startswith("#"):
            continue
        obj = fh[k]
        if isinstance(obj, h5py.Dataset) and obj.ndim == 2:
            arrays[k] = obj
    name, ds = _pick_matrix(arrays)
    if ds is None:
        raise ValueError("No 2-D data matrix found in v7.3 .mat")

    # MATLAB writes HDF5 transposed relative to numpy.
    transposed = ds.shape[0] > ds.shape[1]
    n_ch = ds.shape[1] if transposed else ds.shape[0]

    fs = nlx.DEFAULT_FS
    for key in ("sfx", "fs"):
        if key in fh:
            try:
                fs = float(np.array(fh[key]).reshape(-1)[0])
                break
            except Exception:
                pass
    return {
        "data": ds, "fs": float(fs), "var": name, "labels": None,
        "kept": None, "badch": None, "handle": fh, "h5_transposed": transposed,
        "n_ch": n_ch,
    }


def _scalar(v):
    if v is None:
        return None
    try:
        return float(np.asarray(v).reshape(-1)[0])
    except Exception:
        return None


def _str_list(v, n):
    if v is None:
        return None
    try:
        arr = np.asarray(v).reshape(-1)
        return [str(x) for x in arr][:n]
    except Exception:
        return None


def _num_list(v, n):
    if v is None:
        return None
    try:
        return [int(x) for x in np.asarray(v).reshape(-1)][:n]
    except Exception:
        return None


def _bool_list(v):
    if v is None:
        return None
    try:
        return [bool(x) for x in np.asarray(v).reshape(-1)]
    except Exception:
        return None


def _open_mat(path):
    p = _load_mat(path)
    data = p["data"]
    if p.get("handle") is not None:
        n_ch = p["n_ch"]
        n_samp = data.shape[0] if p["h5_transposed"] else data.shape[1]
    else:
        n_ch, n_samp = data.shape

    labels = p.get("labels")
    kept = p.get("kept")
    badch = p.get("badch") or []

    channels = []
    for i in range(n_ch):
        num = kept[i] if kept and i < len(kept) else (i + 1)
        lbl = labels[i] if labels and i < len(labels) else ("CSC" + str(num))
        bad = bool(badch[num - 1]) if 0 <= num - 1 < len(badch) else False
        channels.append({"index": i, "number": int(num), "label": str(lbl),
                         "file": None, "bad": bad})

    fs = p["fs"]
    return {
        "ok": True, "source": "mat", "path": path,
        "name": os.path.basename(path), "fs": float(fs),
        "duration_s": float(n_samp / fs) if fs else 0.0,
        "even_only": False, "invert": False, "channels": channels,
        "units": "microvolts", "mat_var": p["var"], "n_samples": int(n_samp),
    }


# --------------------------------------------------------------------------
# Windowed reads
# --------------------------------------------------------------------------
def _read_channel_window(session, ch, t0, t1):
    """Return (samples, actual_t0, fs) for one channel over [t0, t1) seconds."""
    if session["source"] == "demo":
        return demo.read_window(session, ch, t0, t1)
    if session["source"] == "ncs":
        return nlx.read_ncs_range(ch["file"], t0, t1, invert=session.get("invert", True))

    p = _load_mat(session["path"])
    fs = p["fs"]
    i0 = max(0, int(np.floor(t0 * fs)))
    i1 = max(i0, int(np.ceil(t1 * fs)))
    data = p["data"]
    idx = ch["index"]

    if p.get("handle") is not None:
        limit = data.shape[0] if p["h5_transposed"] else data.shape[1]
        i1 = min(i1, limit)
        if i1 <= i0:
            return np.empty(0, dtype=np.float32), i0 / fs, fs
        seg = data[i0:i1, idx] if p["h5_transposed"] else data[idx, i0:i1]
        seg = np.asarray(seg, dtype=np.float32)
    else:
        i1 = min(i1, data.shape[1])
        if i1 <= i0:
            return np.empty(0, dtype=np.float32), i0 / fs, fs
        seg = np.asarray(data[idx, i0:i1], dtype=np.float32)

    return seg, i0 / fs, fs


def apply_filters(x, fs, highpass=0.0, lowpass=0.0, notch=0.0):
    """Zero-phase Butterworth band shaping (filtfilt -> no phase distortion).

    Matches the xplorefinder low/high pass controls; 0 disables a stage.
    """
    if x.size == 0 or not HAVE_SCIPY:
        return x
    nyq = fs / 2.0
    # With every stage at zero this used to still promote the whole array to
    # float64 and scan it for NaNs -- on a ten-minute window across 32
    # channels that was seconds of work to return the input unchanged.
    if not ((notch and 0 < notch < nyq)
            or (highpass and 0 < highpass < nyq)
            or (lowpass and 0 < lowpass < nyq)):
        return x

    # float32, not float64. A second-order Butterworth at these corners is
    # comfortably inside single precision, and halving the width of every
    # array halves the memory traffic that dominates a long window.
    y = x.astype(np.float32, copy=True)

    # NaN padding from CSC2LL_uV_mex_disk would poison filtfilt -- bridge it.
    nan_mask = ~np.isfinite(y)
    if nan_mask.any():
        if nan_mask.all():
            return x
        good = np.flatnonzero(~nan_mask)
        y = np.interp(np.arange(y.size), good, y[good])

    try:
        if notch and 0 < notch < nyq:
            y = _notch(y, fs, notch)
        if highpass and 0 < highpass < nyq:
            y = _highpass(y, fs, highpass)
        if lowpass and 0 < lowpass < nyq:
            y = sosfiltfilt(butter(4, lowpass / nyq, btype="lowpass", output="sos"), y)
    except Exception:
        return x

    if nan_mask.any():
        y[nan_mask] = np.nan
    return y.astype(np.float32, copy=False)


# Never decimate below this, so a notch or a high-pass still has room to
# work and the envelope keeps some detail within a pixel column.
MIN_FILTER_FS = 400.0


# Above this ratio of sample rate to corner frequency, a narrow filter is
# computed by subtracting a coarse estimate of the band it removes.
BASELINE_RATIO = 60

# ...but only once the array is big enough for the direct filter to be slow.
# The shortcut is accurate to well under a pixel, not exact, so there is no
# reason to accept even that on a window where the exact filter is cheap. Two
# million samples is a bit over a minute at 30 kHz -- past the point where a
# fraction of a microvolt could be visible at all.
COARSE_MIN_SAMPLES = 2_000_000


def _subtract_coarse(y, fs, target_fs, make_component):
    """Remove a narrow band by measuring it coarsely and subtracting it.

    Some of the filters here have their action packed into a tiny fraction of
    the spectrum: a 1 Hz high-pass at 30 kHz only touches drift, and a 60 Hz
    notch only touches 60 Hz. Running either directly over a ten-minute window
    is eighteen million samples through a zero-phase filter, per channel, to
    change almost nothing.

    Both are subtractive -- `highpass(x) = x - baseline(x)` and
    `notch(x) = x - hum(x)` -- so the part being removed can be measured on a
    heavily decimated copy, stretched back and subtracted. The full-rate
    detail never goes through a filter at all, so what comes out is the
    original trace minus the offending band, not a smoothed version of it.

    `make_component(coarse, fs_coarse)` returns the band to remove, at the
    coarse rate. `y` is modified in place: it is already a private copy made
    by apply_filters, and at this size another one matters.
    """
    if y.size < COARSE_MIN_SAMPLES:
        return None                      # exact filter is affordable here
    q = int(max(1, min(fs // target_fs, y.size // 64)))
    if q < 4:
        return None                      # not worth it; caller filters direct

    n = (y.size // q) * q
    if n < 8 * q:
        return None
    coarse = y[:n].reshape(-1, q).mean(axis=1, dtype=np.float64)
    comp = make_component(coarse, fs / q)
    if comp is None:
        return None
    comp = np.asarray(comp, dtype=np.float32)

    # Subtract through a strided view, one broadcast, in place. np.interp
    # would want both grids as full-size float64 -- three arrays of eighteen
    # million doubles per channel -- and the blocks are uniform, so none of
    # that generality is needed. The ramp is q elements long and broadcasts
    # across every block at once.
    nb = comp.size - 1
    if nb < 1:
        return y - np.float32(comp[0])

    ramp = np.arange(q, dtype=np.float32) / np.float32(q)
    half = q // 2
    body = y[half:half + nb * q].reshape(nb, q)
    lo = comp[:-1, None]
    body -= lo + (comp[1:, None] - lo) * ramp

    # The half block at each end lies outside the interpolated span; hold the
    # nearest value there rather than leaving the band in.
    y[:half] -= comp[0]
    y[half + nb * q:] -= comp[-1]
    return y


def _highpass(y, fs, corner):
    """High-pass: the signal minus its own low-frequency baseline."""
    direct = lambda: sosfiltfilt(
        butter(2, corner / (fs / 2.0), btype="highpass", output="sos"), y)
    if fs / max(corner, 1e-9) < BASELINE_RATIO:
        return direct()

    def baseline(coarse, fs_c):
        # Twenty times the corner leaves plenty of room for a 2nd-order knee.
        return coarse - sosfiltfilt(
            butter(2, corner / (fs_c / 2.0), btype="highpass",
                   output="sos"), coarse)

    out = _subtract_coarse(y, fs, 20.0 * corner, baseline)
    return out if out is not None else direct()


def _notch(y, fs, freq, q_factor=30.0):
    """Notch: the signal minus the narrow band around `freq`."""
    def direct():
        b, a = iirnotch(freq / (fs / 2.0), q_factor)
        return sosfiltfilt(tf2sos(b, a), y)

    if fs / max(freq, 1e-9) < BASELINE_RATIO:
        return direct()

    def hum(coarse, fs_c):
        if freq >= fs_c / 2.0:
            return None
        b, a = iirnotch(freq / (fs_c / 2.0), q_factor)
        return coarse - sosfiltfilt(tf2sos(b, a), coarse)

    # Forty times the notch frequency, not ten. The hum is a sinusoid that
    # gets linearly interpolated back to full rate, and at ten samples per
    # cycle that interpolation alone loses several percent of its amplitude --
    # which is 5 uV of mains left in the trace. Forty samples per cycle puts
    # the error under a tenth of a percent, and the coarse array is still
    # small enough that the filter on it costs nothing.
    out = _subtract_coarse(y, fs, 40.0 * freq, hum)
    return out if out is not None else direct()


def _prep_for_filter(x, fs, highpass, lowpass, notch, px, span):
    """Down-sample before filtering, when the filter makes that lossless.

    Filtering a ten-minute window at 30 kHz is 18 M samples per channel run
    through three zero-phase stages -- half a minute across 32 channels. But a
    70 Hz low-pass says outright that nothing above 70 Hz survives, so the
    work can be done at a few hundred Hz instead and the result is the same
    signal. Only ever applied when a low-pass is set: without one there is no
    band we are entitled to throw away.

    Returns (x, fs) -- unchanged if decimating would not be safe or useful.
    """
    if not (HAVE_SCIPY and lowpass and lowpass > 0):
        return x, fs
    if x.size == 0 or span <= 0:
        return x, fs

    # Keep well clear of the low-pass corner and of the notch, and keep at
    # least a few samples per pixel column so the envelope still means
    # something inside one.
    need = max(4.0 * lowpass,
               4.0 * (notch or 0.0),
               4.0 * (highpass or 0.0),
               8.0 * px / span,
               MIN_FILTER_FS)
    q = int(fs // need)
    if q < 4:                      # not worth the resampling pass
        return x, fs

    # A boxcar (block mean) rather than a polyphase FIR. resample_poly builds
    # an anti-alias filter proportional to q and convolves at the INPUT rate,
    # so a factor of 75 costs more than the filtering it was meant to save. A
    # block mean is one pass over memory.
    #
    # Its stopband is a sinc rather than a brick wall, which is fine here
    # precisely because `need` keeps the new Nyquist at twice the low-pass or
    # more: anything that folds lands above the low-pass corner and the
    # low-pass then removes it. That guarantee is why this is only ever done
    # when a low-pass is set.
    n = (x.size // q) * q
    if n < 8 * q:
        return x, fs
    y = x[:n].reshape(-1, q).mean(axis=1, dtype=np.float32)
    return y, fs / q


def envelope(x, n_out):
    """Min/max decimate to at most n_out columns, preserving extremes."""
    n = x.size
    if n == 0:
        return np.empty(0), np.empty(0)
    if n <= n_out:
        return x.astype(np.float32), x.astype(np.float32)

    per = int(np.ceil(n / n_out))
    pad = (-n) % per
    if pad:
        x = np.concatenate([x, np.full(pad, np.nan, dtype=x.dtype)])
    blocks = x.reshape(-1, per)
    # An all-NaN block is normal (CSD edge channels, NaN-padded .mat tails)
    # and comes back as NaN, which the JSON layer turns into a gap. But the
    # NaN-aware reductions cost several times the plain ones, and .ncs data
    # never contains a NaN -- so check once and take the fast path when we
    # can. isnan().any() short-circuits in C and is far cheaper than nanmin.
    if np.isnan(x).any():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            lo = np.nanmin(blocks, axis=1)
            hi = np.nanmax(blocks, axis=1)
    else:
        lo = blocks.min(axis=1)
        hi = blocks.max(axis=1)
    return lo.astype(np.float32, copy=False), hi.astype(np.float32, copy=False)


# At most this many samples per channel go into the percentile that sets the
# display scale. 20 k is far more than enough for a 99.5th percentile and puts
# a hard ceiling on the cost regardless of how far out the window is zoomed.
SCALE_SAMPLE_MAX = 20000


def _scale_sample(x):
    """|x| at a stride, for estimating the display scale cheaply."""
    if x.size == 0:
        return np.empty(0, dtype=np.float32)
    step = max(1, x.size // SCALE_SAMPLE_MAX)
    s = np.abs(x[::step])
    if not np.isfinite(s).all():
        s = s[np.isfinite(s)]
    return s.astype(np.float32, copy=False)


def compute_csd(traces, spacing_um=50.0):
    """Second spatial derivative across channels (CSD), as in myCSDPP2.m.

    traces: [nCh x nSamp]. Edge channels have no CSD and come back as NaN.
    """
    if traces.shape[0] < 3:
        return np.full_like(traces, np.nan)
    h = spacing_um * 1e-3                       # um -> mm
    csd = np.full_like(traces, np.nan, dtype=np.float32)
    csd[1:-1] = -(traces[:-2] - 2.0 * traces[1:-1] + traces[2:]) / (h * h)
    return csd


def _json_row(arr):
    """numpy row -> JSON list with NaN as null (JSON has no NaN)."""
    return [None if not np.isfinite(v) else float(v) for v in arr]


def get_window(session, t0, t1, channels=None, px=1400,
               highpass=0.0, lowpass=0.0, notch=0.0, mode="voltage",
               spacing_um=50.0, ylim=None):
    """Build the payload the viewer draws: per-channel min/max envelopes."""
    all_ch = session["channels"]
    if channels:
        sel = [all_ch[i] for i in channels if 0 <= i < len(all_ch)]
    else:
        sel = all_ch
    if not sel:
        return {"ok": False, "error": "No channels selected."}

    fs = session["fs"]
    t0 = max(0.0, float(t0))
    t1 = max(t0 + 1.0 / fs, float(t1))
    px = int(max(64, min(px, 4000)))

    # A ten-minute window at 30 kHz is 18 M samples per channel. Holding all
    # 32 of those in one array is 2.3 GB, and only CSD -- a derivative across
    # channels -- actually needs them side by side. Everything else is
    # enveloped a channel at a time, so peak memory is one channel's worth
    # however far out the view is zoomed.
    needs_stack = mode == "csd"

    rows, filtered = [], []
    actual_t0, actual_fs = t0, fs
    width = 0
    for ch in sel:
        seg, seg_t0, seg_fs = _read_channel_window(session, ch, t0, t1)
        actual_t0, actual_fs = seg_t0, seg_fs
        seg, seg_fs = _prep_for_filter(seg, seg_fs, highpass, lowpass,
                                       notch, px, t1 - t0)
        actual_fs = seg_fs
        seg = apply_filters(seg, seg_fs, highpass, lowpass, notch)
        width = max(width, seg.size)
        if needs_stack:
            filtered.append(seg)
        else:
            rows.append((ch, envelope(seg, px), _scale_sample(seg)))

    if width == 0:
        return {"ok": False, "error": "No samples in that time range."}

    if needs_stack:
        stack = np.full((len(filtered), width), np.nan, dtype=np.float32)
        for i, f in enumerate(filtered):
            stack[i, :f.size] = f
        filtered = None                       # release before the derivative
        stack = compute_csd(stack, spacing_um)
        rows = [(ch, envelope(row, px), _scale_sample(row))
                for ch, row in zip(sel, stack)]
        stack = None

    series = []
    samples = []
    for ch, (lo, hi), sample in rows:
        series.append({
            "label": ch["label"], "number": ch["number"], "index": ch["index"],
            "bad": ch["bad"],
            "min": _json_row(lo),
            "max": _json_row(hi),
        })
        if sample.size:
            samples.append(sample)

    # The display scale used to come from a 99.5th percentile of every sample
    # in the window, which meant masking out 576 M values and partitioning the
    # result -- seconds of work for one number. A strided sample of the same
    # data gives the same percentile to well inside a pixel.
    pool = np.concatenate(samples) if samples else np.empty(0, dtype=np.float32)
    robust_auto = float(np.percentile(pool, 99.5)) if pool.size else 1.0
    abs_max = float(pool.max()) if pool.size else 1.0

    # A pinned amplitude scale keeps traces comparable while scrolling and lets
    # two panes be read against each other; without it every window rescales
    # itself and apparent amplitude becomes meaningless.
    robust = robust_auto
    manual = False
    if ylim is not None:
        try:
            v = abs(float(ylim))
            if np.isfinite(v) and v > 0:
                robust, manual = v, True
        except (TypeError, ValueError):
            pass

    return {
        "ok": True, "t0": float(actual_t0),
        "t1": float(actual_t0 + width / actual_fs),
        "fs": float(actual_fs), "n_points": int(len(series[0]["min"])),
        "mode": mode,
        "units": "uV" if mode == "voltage" else "uA/mm3",
        "series": series,
        "robust_max": robust,
        "robust_auto": robust_auto,
        "ylim_manual": manual,
        "abs_max": abs_max,
    }


# --------------------------------------------------------------------------
# Event overlays (LLspikedetector output: ets = times, ech = channels)
# --------------------------------------------------------------------------
def load_events(path):
    """Load IED event marks from an ets/ech .mat, .csv or .xlsx."""
    if not os.path.exists(path):
        return {"ok": False, "error": "Not found: " + path}
    ext = os.path.splitext(path)[1].lower()

    if ext == ".mat":
        try:
            p = _load_mat(path)
            arr = np.asarray(p["data"][:]) if p.get("handle") is not None \
                else np.asarray(p["data"])
            if arr.ndim == 1:
                arr = arr.reshape(-1, 1)
            if arr.shape[0] < arr.shape[1]:
                arr = arr.T
            times = arr[:, 0].astype(float)
            chans = arr[:, 1].astype(int) if arr.shape[1] > 1 else None
            return {"ok": True, "times": times.tolist(),
                    "channels": chans.tolist() if chans is not None else None,
                    "n": int(times.size)}
        except Exception as exc:
            return {"ok": False, "error": "Could not read events: " + str(exc)}

    if ext in (".csv", ".xlsx", ".xls"):
        try:
            import pandas as pd
            df = pd.read_csv(path) if ext == ".csv" else pd.read_excel(path)
            cols = {str(c).lower().strip(): c for c in df.columns}
            tcol = None
            for k in ("time", "times", "ets", "t", "onset"):
                if k in cols:
                    tcol = cols[k]
                    break
            if tcol is None:
                tcol = df.columns[0]
            ccol = None
            for k in ("channel", "ch", "ech", "chan"):
                if k in cols:
                    ccol = cols[k]
                    break
            times = pd.to_numeric(df[tcol], errors="coerce").dropna()
            chans = None
            if ccol is not None:
                chans = pd.to_numeric(df[ccol], errors="coerce").fillna(0).astype(int).tolist()
            return {"ok": True, "times": times.tolist(), "channels": chans,
                    "n": int(times.size)}
        except Exception as exc:
            return {"ok": False, "error": "Could not read events: " + str(exc)}

    return {"ok": False, "error": "Unsupported event file: " + ext}
