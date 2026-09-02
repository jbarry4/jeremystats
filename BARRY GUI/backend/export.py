"""
export.py -- Publication-quality PNG / PDF / SVG rendering of the CSC view.

The browser canvas is for interaction; export re-renders the same window with
matplotlib so PDF and SVG come out as true vectors (editable in Illustrator /
Inkscape) rather than a screenshot of a canvas.

Rendered at a much higher point budget than the on-screen view, so exported
traces carry detail the screen could not show.
"""
from __future__ import annotations

import io
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

from . import csc

# UVM palette on a white page: Catamount Green traces, gold reserved for
# emphasis. Exports stay light regardless of the UI theme -- they are headed
# for a figure panel or a slide, not a screen at midnight.
UVM_GREEN = "#154734"
UVM_GOLD = "#FFB81C"

INK = "#0c1f17"
MUTED = "#5f7168"
GRID = "#dde7e2"
TRACE = UVM_GREEN
BAD = "#a86a00"
EVENT = "#c0392b"


def render_window(session, spec, fmt="png", dpi=200):
    """Render the current viewer window to `fmt`. Returns bytes."""
    t0 = float(spec.get("t0", 0.0))
    t1 = float(spec.get("t1", t0 + 10.0))
    channels = spec.get("channels") or None
    gain = float(spec.get("gain", 1.0)) or 1.0
    mode = spec.get("mode", "voltage")
    spacing = float(spec.get("spacing_um", 50.0))
    events = spec.get("events") or []
    title = spec.get("title") or session.get("name", "CSC")
    width_in = float(spec.get("width_in", 11.0))
    height_in = float(spec.get("height_in", 8.5))
    show_grid = bool(spec.get("grid", True))
    normalize = spec.get("normalize", "shared")

    # Export at higher fidelity than the screen view.
    px = int(max(1200, min(width_in * dpi, 6000)))

    win = csc.get_window(
        session, t0, t1, channels=channels, px=px,
        highpass=float(spec.get("highpass", 0) or 0),
        lowpass=float(spec.get("lowpass", 0) or 0),
        notch=float(spec.get("notch", 0) or 0),
        mode=mode, spacing_um=spacing)
    if not win.get("ok"):
        raise ValueError(win.get("error", "Could not read that window."))

    series = win["series"]
    n = len(series)
    times = np.linspace(win["t0"], win["t1"], win["n_points"])

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    scale = win["robust_max"] or 1.0
    if scale <= 0:
        scale = 1.0
    step = 2.0                                   # one channel lane = 2 units

    for i, s in enumerate(series):
        lo = np.array([np.nan if v is None else v for v in s["min"]], dtype=float)
        hi = np.array([np.nan if v is None else v for v in s["max"]], dtype=float)
        if normalize == "per":
            local = np.nanmax(np.abs(np.concatenate([lo, hi]))) or 1.0
            k = gain / local
        else:
            k = gain / scale

        base = (n - 1 - i) * step
        color = BAD if s["bad"] else TRACE
        # Envelope band + center line: identical to what the canvas draws.
        ax.fill_between(times, base + lo * k, base + hi * k,
                        color=color, linewidth=0.0, alpha=0.95, zorder=2)
        ax.plot(times, base + (lo + hi) * 0.5 * k, color=color,
                linewidth=0.35, zorder=3, solid_joinstyle="round")

    for et in events:
        if win["t0"] <= et <= win["t1"]:
            ax.axvline(et, color=EVENT, linewidth=0.7, alpha=0.55,
                       zorder=1, dashes=(3, 2))

    ax.set_yticks([(n - 1 - i) * step for i in range(n)])
    ax.set_yticklabels([s["label"] for s in series], fontsize=7, color=INK)
    ax.set_ylim(-step, (n - 1) * step + step)
    ax.set_xlim(win["t0"], win["t1"])
    ax.set_xlabel("Time (s)", fontsize=9, color=INK)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=10, steps=[1, 2, 2.5, 5, 10]))
    ax.tick_params(axis="x", labelsize=8, colors=MUTED)
    ax.tick_params(axis="y", length=0)

    if show_grid:
        ax.grid(axis="x", color=GRID, linewidth=0.5, zorder=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)

    unit = win["units"]
    sub = "%s  |  %.3f-%.3f s  |  %d ch  |  %s" % (
        mode.upper(), win["t0"], win["t1"], n, unit)
    filt = []
    if spec.get("highpass"):
        filt.append("HP %.4g Hz" % float(spec["highpass"]))
    if spec.get("lowpass"):
        filt.append("LP %.4g Hz" % float(spec["lowpass"]))
    if spec.get("notch"):
        filt.append("notch %.4g Hz" % float(spec["notch"]))
    if filt:
        sub += "  |  " + ", ".join(filt)

    ax.set_title(title, fontsize=11, color=UVM_GREEN, loc="left", pad=14, weight="bold")
    ax.text(0.0, 1.005, sub, transform=ax.transAxes, fontsize=7.5,
            color=MUTED, va="bottom")

    # Vertical scale bar: one lane equals this many uV at the current gain.
    per_lane = scale * step / gain if gain else scale
    ax.text(1.0, 1.005, "lane = %.3g %s" % (per_lane, unit),
            transform=ax.transAxes, fontsize=7.5, color=MUTED,
            va="bottom", ha="right")

    fig.tight_layout()

    buf = io.BytesIO()
    save_kw = {"format": fmt, "facecolor": "white", "bbox_inches": "tight"}
    if fmt == "png":
        save_kw["dpi"] = dpi
    fig.savefig(buf, **save_kw)
    plt.close(fig)
    return buf.getvalue()


MIME = {
    "png": "image/png",
    "pdf": "application/pdf",
    "svg": "image/svg+xml",
}
