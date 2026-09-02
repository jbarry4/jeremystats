"""
analysis.py -- The modular panel renderers behind Xplorefinder's figure builder.

Each panel is an independent unit that takes a session plus a time window and
returns something drawable. Panels compose freely: voltage traces on top, a CSD
raster under it, a scalogram of one channel beside that.

Panel kinds
    traces        stacked waveforms (vector, drawn by the browser)
    voltage       voltage raster, channels x time   (imagesc + jet)
    csd           current source density raster      (myCSDPP2 + jet)
    theta         theta-band raster, optional voltage contour overlay
    spectrogram   single-channel STFT
    scalogram     single-channel continuous wavelet transform

Image panels are rendered server-side to PNG and handed to the browser as a
data URI. That keeps the payload small (a raster is an image, not geometry) and
means the on-screen colormap is exactly the one matplotlib will use at export.

Conventions follow the MATLAB components they mirror:
    VoltageRaster.m           imagesc(t, 1:nCh, D); colormap(jet)
    myCSDPP2.m                csd = -(x[i+1] - 2x[i] + x[i-1]), then interp2
    Scalogram_..._Pipeline.m  cwt over [20 1000] Hz, clim from 99.5th pct
                              with a 4-decade dynamic range, colormap(jet)
"""
from __future__ import annotations

import base64
import io
import warnings

import numpy as np

import matplotlib
matplotlib.use("Agg")

import matplotlib.colors as mcolors

from . import csc

# Colormaps offered in the UI. `jet` leads because it is what every existing
# figure in the repo uses; the perceptually-uniform maps follow for new work.
COLORMAPS = [
    {"id": "jet", "name": "Jet", "note": "lab standard, matches existing figures"},
    {"id": "turbo", "name": "Turbo", "note": "jet-like but perceptually smoother"},
    {"id": "viridis", "name": "Viridis", "note": "perceptually uniform"},
    {"id": "plasma", "name": "Plasma", "note": "perceptually uniform"},
    {"id": "inferno", "name": "Inferno", "note": "perceptually uniform"},
    {"id": "magma", "name": "Magma", "note": "perceptually uniform"},
    {"id": "cividis", "name": "Cividis", "note": "color-vision friendly"},
    {"id": "RdBu_r", "name": "Red-Blue", "note": "diverging, good for CSD"},
    {"id": "seismic", "name": "Seismic", "note": "diverging, strong center"},
    {"id": "bwr", "name": "Blue-White-Red", "note": "diverging"},
    {"id": "PuOr_r", "name": "Purple-Orange", "note": "diverging, CVD safe"},
    {"id": "gray", "name": "Grayscale", "note": "print safe"},
    {"id": "bone", "name": "Bone", "note": "cool grayscale"},
]
COLORMAP_IDS = {c["id"] for c in COLORMAPS}

PANELS = [
    {"id": "traces", "name": "Voltage traces", "kind": "vector",
     "note": "Stacked per-channel waveforms"},
    {"id": "voltage", "name": "Voltage raster", "kind": "image",
     "note": "Channels x time heatmap, as VoltageRaster.m"},
    {"id": "csd", "name": "CSD raster", "kind": "image",
     "note": "Current source density, as myCSDPP2.m"},
    {"id": "theta", "name": "Theta raster", "kind": "image",
     "note": "Theta-band (4-12 Hz) raster with optional voltage contours"},
    {"id": "spectrogram", "name": "Spectrogram", "kind": "image",
     "single_channel": True, "note": "Short-time Fourier transform of one channel"},
    {"id": "scalogram", "name": "Scalogram", "kind": "image",
     "single_channel": True, "note": "Continuous wavelet transform of one channel"},
]


class PanelError(Exception):
    """Panel failure carrying a message meant to be shown to the user."""


# --------------------------------------------------------------------------
# Shared data access
# --------------------------------------------------------------------------
def _stack(session, spec, channels=None):
    """Read a [nCh x nSamp] microvolt block for the window, filters applied."""
    all_ch = session["channels"]
    idx = channels if channels is not None else spec.get("channels")
    sel = [all_ch[i] for i in idx if 0 <= i < len(all_ch)] if idx else all_ch
    if not sel:
        raise PanelError("No channels selected for this panel.")

    t0 = float(spec.get("t0", 0.0))
    t1 = float(spec.get("t1", t0 + 1.0))
    if t1 <= t0:
        raise PanelError("The time window is empty (t1 must be after t0).")

    hp = float(spec.get("highpass", 0) or 0)
    lp = float(spec.get("lowpass", 0) or 0)
    notch = float(spec.get("notch", 0) or 0)

    rows, actual_t0, fs = [], t0, session["fs"]
    for ch in sel:
        seg, seg_t0, seg_fs = csc._read_channel_window(session, ch, t0, t1)
        actual_t0, fs = seg_t0, seg_fs
        rows.append(csc.apply_filters(seg, seg_fs, hp, lp, notch))

    width = max((r.size for r in rows), default=0)
    if width == 0:
        raise PanelError(
            "No samples in %.3f-%.3f s. The window may be past the end of the "
            "recording (%.1f s)." % (t0, t1, session.get("duration_s", 0)))

    stack = np.full((len(rows), width), np.nan, dtype=np.float32)
    for i, r in enumerate(rows):
        stack[i, :r.size] = r
    return stack, sel, float(actual_t0), float(fs)


def _bad_mask(sel, bad_numbers):
    """Which selected rows are marked bad, by CSC channel number."""
    bad = set(int(b) for b in (bad_numbers or []))
    return np.array([ch["number"] in bad for ch in sel], dtype=bool)


def _drop_bad(stack, sel, bad_numbers, mode="nan"):
    """Bad channels distort a raster's color scale, so handle them explicitly."""
    mask = _bad_mask(sel, bad_numbers)
    if not mask.any():
        return stack, sel, mask
    if mode == "remove":
        keep = ~mask
        return stack[keep], [c for c, k in zip(sel, keep) if k], mask[keep]
    if mode == "interpolate":
        out = stack.copy()
        good = np.flatnonzero(~mask)
        if good.size >= 2:
            for i in np.flatnonzero(mask):
                lo = good[good < i]
                hi = good[good > i]
                if lo.size and hi.size:
                    a, b = lo[-1], hi[0]
                    w = (i - a) / float(b - a)
                    out[i] = (1 - w) * stack[a] + w * stack[b]
                elif lo.size:
                    out[i] = stack[lo[-1]]
                elif hi.size:
                    out[i] = stack[hi[0]]
        return out, sel, mask
    out = stack.copy()
    out[mask] = np.nan
    return out, sel, mask


# --------------------------------------------------------------------------
# Image encoding
# --------------------------------------------------------------------------
def get_cmap(cmap_id):
    """Resolve a colormap id, falling back to the lab default."""
    try:
        return matplotlib.colormaps[cmap_id if cmap_id in COLORMAP_IDS else "jet"]
    except Exception:
        return matplotlib.colormaps["viridis"]


def _encode_image(matrix, cmap_id, clim, upsample=1):
    """Color-map a 2-D array straight to a base64 PNG data URI.

    Encoding the array itself rather than a matplotlib figure keeps the image
    pixel-exact and small: axes, ticks and labels are drawn by the browser (or
    by the exporter), never baked into the data.
    """
    lo, hi = clim
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        lo, hi = -1.0, 1.0

    m = np.asarray(matrix, dtype=np.float64)
    if upsample and upsample > 1:
        m = _interp2(m, upsample)

    norm = mcolors.Normalize(vmin=lo, vmax=hi, clip=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rgba = get_cmap(cmap_id)(norm(m), bytes=True)
    # NaN (bad or missing channels) becomes transparent rather than a color
    # that could be mistaken for data.
    rgba[..., 3] = np.where(np.isfinite(m), 255, 0).astype(np.uint8)

    from matplotlib.image import imsave
    buf = io.BytesIO()
    imsave(buf, rgba, format="png", origin="upper")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _interp2(m, factor):
    """Bilinear upsample, the numpy equivalent of MATLAB's interp2 'linear'.

    myCSDPP2 does exactly this before plotting, which is where the
    'Interpolated_For_Viz' odd channels in the stats tables come from.
    """
    factor = int(max(1, factor))
    if factor == 1:
        return m
    rows, cols = m.shape
    yi = np.linspace(0, rows - 1, (rows - 1) * factor + 1)
    xi = np.linspace(0, cols - 1, min((cols - 1) * factor + 1, 4000))

    y0 = np.clip(np.floor(yi).astype(int), 0, rows - 1)
    y1 = np.clip(y0 + 1, 0, rows - 1)
    wy = (yi - y0)[:, None]
    top = m[y0] * (1 - wy) + m[y1] * wy

    x0 = np.clip(np.floor(xi).astype(int), 0, cols - 1)
    x1 = np.clip(x0 + 1, 0, cols - 1)
    wx = (xi - x0)[None, :]
    return top[:, x0] * (1 - wx) + top[:, x1] * wx


def _robust_clim(m, pct=99.5, symmetric=True, dyn_range=None):
    """Color limits from a robust percentile, as the MATLAB components do."""
    finite = m[np.isfinite(m)]
    if finite.size == 0:
        return (-1.0, 1.0)
    if symmetric:
        hi = float(np.percentile(np.abs(finite), pct))
        if hi <= 0:
            hi = float(np.max(np.abs(finite))) or 1.0
        return (-hi, hi)
    hi = float(np.percentile(finite, pct))
    if dyn_range:
        lo = hi - abs(dyn_range)
    else:
        lo = float(np.percentile(finite, 100 - pct))
    if hi <= lo:
        hi = lo + 1.0
    return (lo, hi)


def _decimate_cols(m, max_cols=2000):
    """Cap raster width; a raster wider than the screen buys nothing."""
    if m.shape[1] <= max_cols:
        return m
    step = int(np.ceil(m.shape[1] / max_cols))
    n = (m.shape[1] // step) * step
    # A block that is entirely NaN (a bad channel) averages to NaN by design.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(m[:, :n].reshape(m.shape[0], -1, step), axis=2)


# --------------------------------------------------------------------------
# Panels
# --------------------------------------------------------------------------
def describe_input(session, spec, used=None):
    """One line saying what this analysis actually ran on.

    Every panel and the spike detector work on the window, channels and
    filters that are on screen at the time. That is the right default, but it
    means the same button gives different answers ten seconds apart -- so the
    answer should carry the question with it. This is that line, and it goes
    in the corner of the panel and beside the detector's result.
    """
    t0 = float(spec.get("t0", 0) or 0)
    t1 = float(spec.get("t1", 0) or 0)
    span = max(0.0, t1 - t0)

    hp = float(spec.get("highpass", 0) or 0)
    lp = float(spec.get("lowpass", 0) or 0)
    notch = float(spec.get("notch", 0) or 0)
    if hp and lp:
        band = "%g-%g Hz" % (hp, lp)
    elif hp:
        band = ">%g Hz" % hp
    elif lp:
        band = "<%g Hz" % lp
    else:
        band = "unfiltered"
    if notch:
        band += " +%gHz notch" % notch

    if used is not None:
        n_ch = len(used)
    else:
        chans = spec.get("channels")
        n_ch = len(chans) if chans else len(session.get("channels") or [])
    n_bad = len(spec.get("bad_channels") or [])

    bits = [
        "%s-%s (%.3g s)" % (_clock(t0), _clock(t1), span),
        "%d ch" % n_ch,
        band,
    ]
    if n_bad:
        bits.append("%d bad excluded" % n_bad)
    if session.get("invert"):
        bits.append("inverted")
    if session.get("even_only"):
        bits.append("even only")
    return "  \u00b7  ".join(bits)


def _clock(t):
    t = max(0.0, float(t or 0))
    return "%d:%05.2f" % (int(t // 60), t % 60)


def render_panel(session, spec):
    """Render one panel. `spec.panel` selects which."""
    kind = spec.get("panel", "voltage")
    if kind == "traces":
        out = _panel_traces(session, spec)
    elif kind == "voltage":
        out = _panel_raster(session, spec, mode="voltage")
    elif kind == "csd":
        out = _panel_raster(session, spec, mode="csd")
    elif kind == "theta":
        out = _panel_raster(session, spec, mode="theta")
    elif kind == "spectrogram":
        out = _panel_tf(session, spec, method="stft")
    elif kind == "scalogram":
        out = _panel_tf(session, spec, method="cwt")
    else:
        raise PanelError("Unknown panel type '%s'. Available: %s"
                         % (kind, ", ".join(p["id"] for p in PANELS)))

    if isinstance(out, dict) and out.get("ok"):
        out["input"] = describe_input(session, spec,
                                      used=out.get("channels_used"))
    return out


def _panel_traces(session, spec):
    win = csc.get_window(
        session, spec.get("t0", 0), spec.get("t1", 10),
        channels=spec.get("channels"), px=int(spec.get("px", 1400)),
        highpass=float(spec.get("highpass", 0) or 0),
        lowpass=float(spec.get("lowpass", 0) or 0),
        notch=float(spec.get("notch", 0) or 0),
        mode="voltage", spacing_um=float(spec.get("spacing_um", 50) or 50))
    if not win.get("ok"):
        raise PanelError(win.get("error", "Could not read that window."))
    win["panel"] = "traces"
    win["render"] = "vector"
    return win


def _panel_raster(session, spec, mode):
    stack, sel, t0, fs = _stack(session, spec)
    # CSD is a second spatial derivative, so one NaN channel wipes out its two
    # neighbours as well. Interpolating a bad channel from its neighbours keeps
    # the profile intact -- the same thing the pipeline's "Interpolated_For_Viz"
    # channels do. Voltage rasters have no such coupling, so a bad channel is
    # simply left blank there.
    bad_mode = spec.get("bad_mode") or ("interpolate" if mode == "csd" else "nan")
    stack, sel, _bad = _drop_bad(stack, sel, spec.get("bad_channels"),
                                 bad_mode)

    upsample = 1
    if mode == "csd":
        spacing = float(spec.get("spacing_um", 50) or 50)
        if stack.shape[0] < 3:
            raise PanelError(
                "CSD needs at least 3 channels (it is a second spatial "
                "derivative); %d selected." % stack.shape[0])
        matrix = csc.compute_csd(stack, spacing)[1:-1]
        rows = sel[1:-1]
        units = "uA/mm3"
        upsample = int(spec.get("upsample", 2) or 1)
        default_cmap = "jet"
    elif mode == "theta":
        matrix = np.vstack([csc.apply_filters(r, fs, 4.0, 12.0, 0.0) for r in stack])
        rows = sel
        units = "uV (4-12 Hz)"
        default_cmap = "jet"
    else:
        matrix = stack
        rows = sel
        units = "uV"
        default_cmap = "jet"

    matrix = _decimate_cols(matrix, int(spec.get("max_cols", 2000)))

    clim = _explicit_clim(spec)
    if clim is None:
        clim = list(_robust_clim(matrix, float(spec.get("clim_pct", 99.5)),
                                 symmetric=True))
    clim = [float(clim[0]), float(clim[1])]

    cmap = spec.get("cmap", default_cmap)
    data_uri = _encode_image(matrix, cmap, clim, upsample=upsample)

    n_samp = stack.shape[1]
    # Recompute the bad flags against the rows actually drawn: CSD drops the
    # first and last channel, so the mask from the full stack no longer lines up.
    row_bad = _bad_mask(rows, spec.get("bad_channels"))
    return {
        "ok": True, "panel": mode, "render": "image",
        "image": data_uri,
        # Row 0 of the image sits at the TOP of the extent (origin="upper"),
        # so the y axis runs from len(rows) at the top down to 1 at the bottom.
        "extent": [t0, t0 + n_samp / fs, 0.5, len(rows) + 0.5],
        "rows": [{"label": c["label"], "number": c["number"], "bad": bool(b)}
                 for c, b in zip(rows, row_bad)],
        "clim": clim, "cmap": cmap, "units": units,
        "clim_auto": list(_robust_clim(matrix, float(spec.get("clim_pct", 99.5)),
                                       symmetric=True)),
        "clim_manual": _explicit_clim(spec) is not None,
        "shape": list(matrix.shape),
        "upsample": upsample,
        "t0": t0, "t1": t0 + n_samp / fs, "fs": fs,
    }


def _panel_tf(session, spec, method):
    """Time-frequency panel.

    Works on one channel or several. With several, `tf_mode` decides:
        mean   average the power across channels before converting to dB --
               the usual way to pull a weak rhythm out of the noise
        stack  one spectrogram per channel, stacked vertically, so laminar
               differences stay visible
    """
    ch_list = _tf_channels(spec, session)
    tf_mode = spec.get("tf_mode", "mean")

    fmin = float(spec.get("fmin", 20) or 20)
    fmax = float(spec.get("fmax", 1000) or 1000)

    stack, sel, t0, fs = _stack(session, spec, channels=ch_list)
    nyq = fs / 2.0
    fmax = min(fmax, nyq * 0.98)
    if fmin >= fmax:
        raise PanelError("Frequency range is empty: fmin %.3g must be below "
                         "fmax %.3g (Nyquist is %.0f Hz)." % (fmin, fmax, nyq))

    powers, freqs, times = [], None, None
    for row, ch in zip(stack, sel):
        y = _fill_gaps(row, ch)
        p, freqs, times = (_stft if method == "stft" else _cwt)(y, fs, fmin, fmax, spec)
        powers.append(p)

    if len(powers) == 1:
        combined = powers[0]
        rows_meta = None
    elif tf_mode == "stack":
        # Pad each block to the same width, then stack top-to-bottom.
        width = min(p.shape[1] for p in powers)
        combined = np.vstack([p[:, :width] for p in powers])
        times = times[:width]
        rows_meta = [{"label": c["label"], "number": c["number"]} for c in sel]
    else:
        width = min(p.shape[1] for p in powers)
        combined = np.mean(np.stack([p[:, :width] for p in powers]), axis=0)
        times = times[:width]
        rows_meta = None

    with np.errstate(divide="ignore", invalid="ignore"):
        db = 10.0 * np.log10(np.maximum(combined, 1e-20))

    # A display-only crop of the frequency axis.
    #
    # This is deliberately not the same thing as fmin/fmax. Those set the band
    # the transform is computed over, which changes the wavelet family, the
    # frequency spacing and therefore the numbers. This just shows a slice of
    # what was already computed -- same analysis, same values, narrower view --
    # so you can look hard at 4-12 Hz without the result depending on the fact
    # that you did.
    view = None
    if not stacked_view(rows_meta):
        view = _freq_view(spec, freqs)
    if view is not None:
        lo_i, hi_i = view
        db = db[lo_i:hi_i + 1]
        freqs = freqs[lo_i:hi_i + 1]

    clim = _explicit_clim(spec)
    if clim is None:
        finite = db[np.isfinite(db)]
        hi = float(np.percentile(finite, float(spec.get("clim_pct", 99.5)))) \
            if finite.size else 0.0
        dyn = float(spec.get("dyn_range_db", 40) or 40)
        clim = [hi - dyn, hi]

    cmap = spec.get("cmap", "jet")
    # Low frequency at the bottom, as MATLAB draws it.
    data_uri = _encode_image(db[::-1], cmap, clim)

    n_ch = len(sel)
    stacked = rows_meta is not None
    cropped = view is not None
    extent_y = [0.5, n_ch + 0.5] if stacked else [float(freqs[0]), float(freqs[-1])]

    return {
        "ok": True, "panel": "spectrogram" if method == "stft" else "scalogram",
        "render": "image", "image": data_uri,
        "extent": [t0 + float(times[0]), t0 + float(times[-1]),
                   extent_y[0], extent_y[1]],
        "clim": [float(clim[0]), float(clim[1])], "cmap": cmap, "units": "dB",
        "channel": {"label": sel[0]["label"], "number": sel[0]["number"],
                    "index": int(sel[0]["index"])} if n_ch == 1 else None,
        "channels_used": [{"label": c["label"], "number": c["number"],
                           "index": c["index"]} for c in sel],
        "tf_mode": "single" if n_ch == 1 else tf_mode,
        "rows": rows_meta,
        "freqs": [float(freqs[0]), float(freqs[-1])],
        "freqs_computed": [float(fmin), float(fmax)],
        "freq_bins": int(len(freqs)),
        "freq_cropped": cropped,
        "log_freq": (method == "cwt") and not stacked,
        "stacked": stacked,
        "shape": list(db.shape),
        "t0": t0 + float(times[0]), "t1": t0 + float(times[-1]), "fs": fs,
        "method": ("STFT" if method == "stft" else "Morlet CWT")
                  + ("" if n_ch == 1 else "  %d ch %s" % (n_ch, tf_mode)),
    }


def stacked_view(rows_meta):
    """A stacked multi-channel panel has channels on its vertical axis, not
    frequency, so there is no frequency axis to crop."""
    return rows_meta is not None


def _freq_view(spec, freqs):
    """Row indices for the requested display band, or None for all of it."""
    lo = spec.get("fview_min")
    hi = spec.get("fview_max")
    if lo is None and hi is None:
        return None
    try:
        lo = float(lo) if lo is not None else float(freqs[0])
        hi = float(hi) if hi is not None else float(freqs[-1])
    except (TypeError, ValueError):
        return None
    if not (hi > lo):
        return None
    # Nothing to do if the band already covers everything computed.
    if lo <= freqs[0] and hi >= freqs[-1]:
        return None

    lo_i = int(np.searchsorted(freqs, lo, side="left"))
    hi_i = int(np.searchsorted(freqs, hi, side="right")) - 1
    lo_i = max(0, min(lo_i, freqs.size - 1))
    hi_i = max(lo_i, min(hi_i, freqs.size - 1))
    # A band narrower than two rows would render as a stripe with no gradient.
    if hi_i - lo_i < 1:
        hi_i = min(freqs.size - 1, lo_i + 1)
    return (lo_i, hi_i)


def _tf_channels(spec, session):
    """Which channels a time-frequency panel should use."""
    explicit = spec.get("tf_channels")
    if explicit:
        return [int(c) for c in explicit]
    ch = spec.get("channel")
    if ch is not None:
        return [int(ch)]
    sel = spec.get("channels") or []
    if sel:
        return [int(sel[0])]
    raise PanelError(
        "A time-frequency panel needs at least one channel. Pick one for this "
        "panel, or select channels in the session.")


def _fill_gaps(row, ch):
    """Bridge NaNs so the transform sees a continuous signal."""
    finite = np.isfinite(row)
    if not finite.any():
        raise PanelError("Channel %s has no finite samples in this window."
                         % ch["label"])
    if finite.all():
        return row
    return np.interp(np.arange(row.size), np.flatnonzero(finite), row[finite])


def _explicit_clim(spec):
    """Honour a user-set color scale; None means 'work it out'."""
    clim = spec.get("clim")
    if not clim or len(clim) != 2:
        return None
    try:
        lo, hi = float(clim[0]), float(clim[1])
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return None
    return [lo, hi]


# How many frequency bins a spectrogram should aim to put inside the band
# actually being looked at. Below about this the picture is visibly banded
# once it is stretched to the height of a pane.
TARGET_FREQ_BINS = 120


def _stft(y, fs, fmin, fmax, spec):
    from scipy.signal import spectrogram as _spec
    nper = int(spec.get("nperseg", 0) or 0)
    if nper <= 0:
        # The segment length was chosen purely for time resolution -- about 40
        # columns a second -- with no regard for how many FFT bins landed in
        # the band being displayed. At 30 kHz over 20-1000 Hz that left 34 bins
        # out of 513: 93% of the transform discarded, and the surviving rows
        # stretched thirteen times to fill a pane, which is what made the
        # picture look blocky.
        #
        # Bin spacing is fs / nperseg, so to get N bins across the band:
        #     nperseg = fs * N / (fmax - fmin)
        # Rounded to a power of two, and bounded so the window stays short
        # enough to keep useful time resolution.
        band = max(1.0, float(fmax) - float(fmin))
        want = fs * TARGET_FREQ_BINS / band
        # Never longer than a quarter of the data, or there are too few
        # columns left to see anything move.
        want = min(want, max(64.0, y.size / 4.0))
        nper = int(2 ** np.round(np.log2(max(64.0, want))))
    nper = int(min(max(32, nper), max(64, y.size)))
    nover = int(nper * float(spec.get("overlap", 0.85) or 0.85))
    nover = min(max(0, nover), nper - 1)

    freqs, times, Sxx = _spec(y, fs=fs, nperseg=nper, noverlap=nover,
                              scaling="density", mode="psd")
    keep = (freqs >= fmin) & (freqs <= fmax)
    if not keep.any():
        raise PanelError(
            "No FFT bins between %.3g and %.3g Hz. The window is too short for "
            "this frequency range -- widen the window or raise fmin."
            % (fmin, fmax))
    return Sxx[keep], freqs[keep], times


def _cwt(y, fs, fmin, fmax, spec):
    """Complex Morlet CWT on log-spaced frequencies.

    MATLAB's cwt uses Morse wavelets; this uses an analytic Morlet, which gives
    the same qualitative time-frequency picture with a comparable time/frequency
    trade-off. The frequency axis is log-spaced, as MATLAB's is.
    """
    # Voices per octave sets the vertical resolution. The default was tuned
    # for a single-channel panel; a stacked one divides the same height
    # between channels, so it needs proportionally more rows to avoid the
    # same banding.
    n_voices = int(spec.get("voices_per_octave", 0) or 0)
    if n_voices <= 0:
        n_voices = 12
        n_stack = len(spec.get("tf_channels") or [])
        if spec.get("tf_mode") == "stack" and n_stack > 1:
            n_voices = int(min(28, 12 * min(n_stack, 3)))
    n_oct = max(1.0, np.log2(fmax / fmin))
    n_freq = int(min(220, max(8, round(n_oct * n_voices))))
    freqs = np.logspace(np.log10(fmin), np.log10(fmax), n_freq)

    # Cap the transform length; a CWT over a long window at high fs is huge.
    max_n = int(spec.get("max_cwt_samples", 200000) or 200000)
    step = 1
    if y.size > max_n:
        step = int(np.ceil(y.size / max_n))
        y = y[::step]
    fs_eff = fs / step

    n = y.size
    if n < 16:
        raise PanelError("Window is too short for a scalogram (%d samples)." % n)

    nfft = int(2 ** np.ceil(np.log2(n * 2)))
    Y = np.fft.fft(y - np.mean(y), nfft)
    omega = 2.0 * np.pi * np.fft.fftfreq(nfft, d=1.0 / fs_eff)

    w0 = float(spec.get("morlet_w0", 6.0) or 6.0)
    power = np.empty((n_freq, n), dtype=np.float64)
    for i, f in enumerate(freqs):
        scale = w0 / (2.0 * np.pi * f)
        sw = scale * omega
        # Analytic Morlet: positive frequencies only.
        psi = np.zeros(nfft)
        pos = sw > 0
        psi[pos] = np.exp(-0.5 * (sw[pos] - w0) ** 2)
        psi *= np.sqrt(2.0 * np.pi * scale * fs_eff)
        coef = np.fft.ifft(Y * psi)[:n]
        power[i] = np.abs(coef) ** 2

    times = np.arange(n) / fs_eff
    power = _decimate_cols(power, int(spec.get("max_cols", 2000)))
    if power.shape[1] != n:
        times = np.linspace(times[0], times[-1], power.shape[1])
    return power, freqs, times


def colormap_swatch(cmap_id, n=32):
    """Small gradient for the colormap picker."""
    cmap_id = cmap_id if cmap_id in COLORMAP_IDS else "jet"
    try:
        cmap = matplotlib.colormaps[cmap_id]
    except Exception:
        cmap = matplotlib.colormaps["jet"]
    cols = cmap(np.linspace(0, 1, n), bytes=True)
    return ["#%02x%02x%02x" % tuple(c[:3]) for c in cols]


# --------------------------------------------------------------------------
# Threshold spike labeling
# --------------------------------------------------------------------------
def detect_spikes(session, spec):
    """Simple amplitude-threshold detector over a time range.

    Deliberately plain: threshold, polarity, refractory period. It is a
    labeling aid, not a replacement for LLspikedetector -- the point is to
    mark things quickly and see them straight away, then commit the ones worth
    keeping.

    Threshold is given either as a multiple of the channel's robust SD
    (median absolute deviation, which a big spike cannot inflate) or as an
    absolute microvolt value.
    """
    t0 = float(spec.get("t0", 0.0))
    t1 = float(spec.get("t1", t0 + 10.0))
    if t1 <= t0:
        raise PanelError("Empty time range for detection.")

    max_span = float(spec.get("max_span_s", 600.0))
    if t1 - t0 > max_span:
        raise PanelError(
            "Detection range is %.0f s; the limit is %.0f s in one pass. "
            "Narrow the window or raise max_span_s." % (t1 - t0, max_span))

    stack, sel, actual_t0, fs = _stack(session, dict(spec, t0=t0, t1=t1))

    mode = spec.get("threshold_mode", "sd")
    k = float(spec.get("threshold", 4.0) or 4.0)
    polarity = spec.get("polarity", "neg")
    refractory = float(spec.get("refractory_ms", 1.0) or 1.0) / 1000.0
    min_gap = max(1, int(refractory * fs))

    bad = set(int(b) for b in (spec.get("bad_channels") or []))
    out, per_channel = [], []

    for row, ch in zip(stack, sel):
        if ch["number"] in bad or ch.get("bad"):
            continue
        x = row[np.isfinite(row)]
        if x.size < 8:
            continue

        # Robust SD: MAD scaled to a Gaussian, so one huge artifact does not
        # raise the threshold above every real event.
        mad = float(np.median(np.abs(x - np.median(x))))
        sd = mad / 0.6745 if mad > 0 else float(np.std(x)) or 1.0
        thr = k * sd if mode == "sd" else abs(k)

        sig = np.nan_to_num(row, nan=0.0)
        if polarity == "neg":
            over = sig <= -thr
        elif polarity == "pos":
            over = sig >= thr
        else:
            over = np.abs(sig) >= thr

        idx = np.flatnonzero(over)
        if idx.size == 0:
            per_channel.append({"label": ch["label"], "number": ch["number"],
                                "n": 0, "threshold_uv": round(thr, 2),
                                "sd_uv": round(sd, 2)})
            continue

        # Collapse each supra-threshold run to its extreme sample, then apply
        # the refractory period.
        breaks = np.flatnonzero(np.diff(idx) > 1)
        runs = np.split(idx, breaks + 1)
        picks = []
        last = -10 ** 9
        for run in runs:
            seg = sig[run]
            j = int(run[int(np.argmin(seg) if polarity == "neg"
                            else np.argmax(np.abs(seg) if polarity == "abs" else seg))])
            if j - last < min_gap:
                continue
            last = j
            picks.append(j)

        for j in picks:
            out.append({
                "start": float(actual_t0 + j / fs),
                "channel": int(ch["number"]),
                "amplitude": float(sig[j]),
                "label": "thr",
                "source": "threshold",
            })
        per_channel.append({"label": ch["label"], "number": ch["number"],
                            "n": len(picks), "threshold_uv": round(thr, 2),
                            "sd_uv": round(sd, 2)})

    out.sort(key=lambda e: e["start"])

    # Optionally merge near-simultaneous hits across channels into one event,
    # the same assumption LLspikedetector makes.
    if spec.get("merge_channels", True) and out:
        window = float(spec.get("merge_ms", 2.0) or 2.0) / 1000.0
        merged, group = [], [out[0]]
        for e in out[1:]:
            if e["start"] - group[0]["start"] <= window:
                group.append(e)
            else:
                merged.append(_merge_group(group))
                group = [e]
        merged.append(_merge_group(group))
        out = merged

    return {
        "ok": True,
        "events": out,
        "n": len(out),
        "input": describe_input(session, spec, used=[c for c in sel]),
        "t0": float(actual_t0), "t1": float(actual_t0 + stack.shape[1] / fs),
        "per_channel": per_channel,
        "params": {"threshold": k, "threshold_mode": mode, "polarity": polarity,
                   "refractory_ms": refractory * 1000.0,
                   "merge_channels": bool(spec.get("merge_channels", True)),
                   "merge_ms": float(spec.get("merge_ms", 2.0) or 2.0),
                   "highpass": spec.get("highpass"), "lowpass": spec.get("lowpass"),
                   "notch": spec.get("notch")},
    }


def _merge_group(group):
    """Represent a cross-channel cluster by its largest deflection."""
    lead = max(group, key=lambda e: abs(e["amplitude"]))
    return {
        "start": float(min(e["start"] for e in group)),
        "channel": lead["channel"],
        "amplitude": lead["amplitude"],
        "n_channels": len(group),
        "channels": sorted({e["channel"] for e in group}),
        "label": "thr",
        "source": "threshold",
    }
