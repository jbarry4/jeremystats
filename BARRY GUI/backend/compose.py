"""
compose.py -- Multi-panel figure composition and export.

The preview/design mode in Xplorefinder builds a layout: a grid of panels, each
one of the analysis kinds, with titles and a metadata block. This module turns
that layout into a real figure at a real size, so what you arrange on screen is
what lands in the PDF.

Everything is drawn with matplotlib, so PDF and SVG come out as true vectors --
except raster panels, which are genuinely images and are embedded as such.

The metadata block is the reproducibility half: who made the figure, from which
session on which machine, with which filters, and the GUI_logs run id that ties
it back to the exact analysis that produced it.
"""
from __future__ import annotations

import io
from datetime import datetime

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.ticker import MaxNLocator

from . import analysis, csc

# UVM palette; exports are always light, since they end up in a paper or a deck.
UVM_GREEN = "#154734"
UVM_GOLD = "#FFB81C"
INK = "#0c1f17"
MUTED = "#5f7168"
GRID = "#dde7e2"
EVENT = "#c0392b"

MIME = {"png": "image/png", "pdf": "application/pdf", "svg": "image/svg+xml"}
PAGE_PRESETS = {
    "letter_landscape": (11.0, 8.5),
    "letter_portrait": (8.5, 11.0),
    "a4_landscape": (11.69, 8.27),
    "a4_portrait": (8.27, 11.69),
    "slide_16_9": (13.333, 7.5),
    "square": (9.0, 9.0),
    "figure_1col": (3.5, 3.0),
    "figure_2col": (7.2, 4.5),
}


class ComposeError(Exception):
    pass


class _Scale:
    """Type sizes and spacing derived from the actual page size.

    A 3.5in journal-column figure and a 13in slide need the same *proportions*,
    not the same point sizes. Everything keys off the smaller page dimension,
    clamped so a huge poster does not end up with absurd 40pt ticks.
    """

    def __init__(self, width, height, layout=None):
        layout = layout or {}
        self.width = width
        self.height = height
        ref = min(width, height)
        # 8.5in (letter short edge) is the reference at which the original
        # hand-tuned sizes looked right.
        self.k = max(0.55, min(1.9, (ref / 8.5) ** 0.62))

        base = float(layout.get("font_scale", 1.0) or 1.0)
        self.k *= max(0.5, min(2.5, base))

        self.title_pt = self._sz(14)
        self.sub_pt = self._sz(9.5)
        self.panel_title_pt = self._sz(10)
        self.label_pt = self._sz(8.5)
        self.tick_pt = self._sz(7.5)
        self.chan_pt = self._sz(6.5)
        self.meta_pt = self._sz(7)
        self.small_pt = self._sz(6.5)

        # More panels need more breathing room between them, not less.
        rows = max(1, int(layout.get("rows") or 1))
        cols = max(1, int(layout.get("cols") or 1))
        self.hspace = 0.34 + 0.10 * min(rows, 4)
        self.wspace = 0.24 + 0.08 * min(cols, 4)

    def _sz(self, pt):
        return round(max(4.0, min(pt * self.k, pt * 1.9)), 2)

    @staticmethod
    def pt(points):
        """Points to inches."""
        return points / 72.0


def _needs_colorbar(panels):
    return any(p.get("panel") != "traces" and p.get("colorbar", True)
               for p in panels)


def render_figure(sessions, layout, fmt="png", dpi=200):
    """Render a full multi-panel layout.

    `sessions` maps a session id -> opened session dict, so a single figure can
    draw panels from more than one recording (a baseline/CNO comparison, say).
    """
    fmt = (fmt or "png").lower()
    if fmt not in MIME:
        raise ComposeError("Unsupported export format '%s'. Use png, pdf or svg."
                           % fmt)

    panels = layout.get("panels") or []
    if not panels:
        raise ComposeError("Nothing to export -- add at least one panel.")

    width, height = _page_size(layout)
    rows = max(1, int(layout.get("rows") or _auto_rows(panels)))
    cols = max(1, int(layout.get("cols") or _auto_cols(panels)))

    # Everything below is expressed in INCHES first, then converted to figure
    # fractions. A fixed fraction is what made the 3.5in preset overlap its own
    # title: 5% of 8.5in is 0.43in and fits a 14pt heading, but 5% of 3in is
    # 0.15in and does not.
    S = _Scale(width, height, layout)

    show_meta = bool(layout.get("show_metadata", True))
    title = (layout.get("title") or "").strip()
    subtitle = (layout.get("subtitle") or "").strip()

    meta_in = (S.pt(7) * 2 + 0.10) if show_meta else 0.0
    title_in = 0.0
    if title:
        title_in += S.pt(S.title_pt) * 1.35
    if subtitle:
        title_in += S.pt(S.sub_pt) * 1.5

    fig = plt.figure(figsize=(width, height), dpi=dpi)
    fig.patch.set_facecolor("white")

    left_in = S.pt(S.tick_pt) * 4.2 + 0.22      # room for y tick labels
    right_in = 0.16 + (0.34 if _needs_colorbar(panels) else 0.0)
    bottom_in = S.pt(S.label_pt) * 2.6 + 0.16   # x label + ticks

    # ax.set_title draws ABOVE the axes box, outside the GridSpec, so the grid
    # has to start lower or the first row's panel titles climb into the figure
    # subtitle -- which is exactly what happened on the 3.5in preset.
    has_panel_titles = any((p.get("title") or "").strip() for p in panels)
    panel_title_in = S.pt(S.panel_title_pt) * 2.1 if has_panel_titles else 0.0

    gs = GridSpec(
        rows, cols, figure=fig,
        left=left_in / width,
        right=1.0 - right_in / width,
        bottom=(bottom_in + meta_in) / height,
        top=1.0 - (0.10 + title_in + panel_title_in) / height,
        hspace=float(layout.get("hspace", S.hspace)),
        wspace=float(layout.get("wspace", S.wspace)))

    problems = []
    for i, p in enumerate(panels):
        try:
            _draw_panel(fig, gs, p, sessions, rows, cols, layout, S)
        except Exception as exc:
            problems.append("Panel %d (%s): %s"
                            % (i + 1, p.get("panel", "?"), exc))
            _draw_error(fig, gs, p, rows, cols, str(exc), S)

    y = 1.0 - 0.06 / height
    if title:
        fig.text(left_in / width, y, title, fontsize=S.title_pt, weight="bold",
                 color=UVM_GREEN, va="top", ha="left")
        y -= (S.pt(S.title_pt) * 1.25) / height
    if subtitle:
        fig.text(left_in / width, y, subtitle, fontsize=S.sub_pt,
                 color=MUTED, va="top", ha="left")

    if show_meta:
        _draw_metadata(fig, layout, sessions, S)

    buf = io.BytesIO()
    save_kw = {"format": fmt, "facecolor": "white"}
    if fmt == "png":
        save_kw["dpi"] = dpi
    fig.savefig(buf, **save_kw)
    plt.close(fig)
    return buf.getvalue(), problems


def _page_size(layout):
    preset = layout.get("page")
    if preset and preset in PAGE_PRESETS:
        return PAGE_PRESETS[preset]
    w = float(layout.get("width_in", 11.0) or 11.0)
    h = float(layout.get("height_in", 8.5) or 8.5)
    return max(2.0, min(w, 60.0)), max(2.0, min(h, 60.0))


def _auto_rows(panels):
    return max((int(p.get("row", 0)) + int(p.get("rowspan", 1))) for p in panels)


def _auto_cols(panels):
    return max((int(p.get("col", 0)) + int(p.get("colspan", 1))) for p in panels)


def _slot(gs, p, rows, cols):
    r = min(max(0, int(p.get("row", 0))), rows - 1)
    c = min(max(0, int(p.get("col", 0))), cols - 1)
    rs = max(1, min(int(p.get("rowspan", 1)), rows - r))
    cs = max(1, min(int(p.get("colspan", 1)), cols - c))
    return gs[r:r + rs, c:c + cs]


def _session_for(p, sessions):
    sid = p.get("session_id") or p.get("session") or "default"
    sess = sessions.get(sid) or sessions.get("default")
    if not sess:
        raise ComposeError("No session loaded for this panel.")
    return sess


def _draw_panel(fig, gs, p, sessions, rows, cols, layout, S=None):
    ax = fig.add_subplot(_slot(gs, p, rows, cols))
    sess = _session_for(p, sessions)

    S = S or _Scale(11.0, 8.5, layout)
    spec = dict(p)
    spec.setdefault("t0", layout.get("t0", 0))
    spec.setdefault("t1", layout.get("t1", 10))
    for key in ("highpass", "lowpass", "notch", "channels", "bad_channels",
                "spacing_um", "cmap"):
        if key not in spec and key in layout:
            spec[key] = layout[key]

    kind = spec.get("panel", "traces")
    if kind == "traces":
        _draw_traces(ax, sess, spec, layout, S)
    else:
        _draw_image_panel(ax, sess, spec, S)

    ttl = (p.get("title") or "").strip()
    if ttl:
        ax.set_title(ttl, fontsize=S.panel_title_pt, color=INK, loc="left",
                     pad=max(2.0, S.pt(S.panel_title_pt) * 40), weight="bold")

    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(labelsize=S.tick_pt, colors=MUTED)


def _draw_error(fig, gs, p, rows, cols, msg, S=None):
    try:
        ax = fig.add_subplot(_slot(gs, p, rows, cols))
    except Exception:
        return
    ax.set_axis_off()
    ax.text(0.5, 0.5, "Panel failed\n\n" + _wrap(msg, 46),
            ha="center", va="center",
            fontsize=(S or _Scale(11.0, 8.5)).small_pt, color=EVENT,
            transform=ax.transAxes)
    ax.set_facecolor("#fdf3f2")


def _wrap(text, width):
    import textwrap
    return "\n".join(textwrap.wrap(str(text), width)[:8])


def _draw_traces(ax, sess, spec, layout, S=None):
    S = S or _Scale(11.0, 8.5, layout)
    win = csc.get_window(
        sess, spec.get("t0", 0), spec.get("t1", 10),
        channels=spec.get("channels"),
        px=int(spec.get("px", 2200)),
        highpass=float(spec.get("highpass", 0) or 0),
        lowpass=float(spec.get("lowpass", 0) or 0),
        notch=float(spec.get("notch", 0) or 0),
        mode="voltage",
        spacing_um=float(spec.get("spacing_um", 50) or 50),
        ylim=spec.get("ylim"))
    if not win.get("ok"):
        raise ComposeError(win.get("error", "Could not read that window."))

    series = win["series"]
    n = len(series)
    times = np.linspace(win["t0"], win["t1"], win["n_points"])
    gain = float(spec.get("gain", 1.0) or 1.0)
    scale = win["robust_max"] or 1.0
    step = 2.0
    bad = set(int(b) for b in (spec.get("bad_channels") or []))
    per_channel = spec.get("normalize") == "per"

    for i, s in enumerate(series):
        lo = np.array([np.nan if v is None else v for v in s["min"]], dtype=float)
        hi = np.array([np.nan if v is None else v for v in s["max"]], dtype=float)
        if per_channel:
            local = np.nanmax(np.abs(np.concatenate([lo, hi])))
            k = gain / (local if local and np.isfinite(local) and local > 0 else 1.0)
        else:
            k = gain / scale
        base = (n - 1 - i) * step
        is_bad = s["bad"] or s["number"] in bad
        color = "#a86a00" if is_bad else UVM_GREEN
        ax.fill_between(times, base + lo * k, base + hi * k, color=color,
                        linewidth=0, alpha=0.95, zorder=2)
        ax.plot(times, base + (lo + hi) * 0.5 * k, color=color,
                linewidth=0.35, zorder=3)

    _draw_events(ax, spec, win["t0"], win["t1"])

    ax.set_yticks([(n - 1 - i) * step for i in range(n)])
    # Thin out channel labels when they would collide at this page size.
    lab_in = S.pt(S.chan_pt) * 1.5
    max_labels = max(2, int((ax.figure.get_size_inches()[1] * 0.6) / lab_in))
    stride = max(1, int(np.ceil(n / max_labels)))
    ax.set_yticklabels(
        [(s["label"] + (" (bad)" if (s["bad"] or s["number"] in bad) else ""))
         if (i % stride == 0) else ""
         for i, s in enumerate(series)], fontsize=S.chan_pt)
    ax.set_ylim(-step, (n - 1) * step + step)
    ax.set_xlim(win["t0"], win["t1"])
    ax.set_xlabel("Time (s)", fontsize=S.label_pt, color=INK)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=max(4, int(6 * S.k)),
                                           steps=[1, 2, 2.5, 5, 10]))
    ax.grid(axis="x", color=GRID, linewidth=0.5, zorder=0)
    ax.tick_params(axis="y", length=0)
    if spec.get("show_scale", True):
        lane = scale * step / gain if gain else scale
        # Inside the axes, top-right. Above the axes it fights the panel title
        # once the page gets small.
        ax.text(0.995, 0.985, "lane %.3g uV%s" % (lane, ", pinned"
                if win.get("ylim_manual") else ""),
                transform=ax.transAxes, fontsize=S.small_pt, color=MUTED,
                ha="right", va="top", zorder=6,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.75,
                          pad=1.2))


def _draw_image_panel(ax, sess, spec, S=None):
    panel = analysis.render_panel(sess, spec)
    img = _decode_data_uri(panel["image"])
    extent = panel["extent"]

    S = S or _Scale(11.0, 8.5)
    ax.imshow(img, aspect="auto", extent=extent, origin="upper",
              interpolation=spec.get("interpolation", "nearest"), zorder=1)
    ax.set_xlabel("Time (s)", fontsize=S.label_pt, color=INK)

    kind = panel["panel"]
    rows = panel.get("rows") or []
    is_tf = kind in ("spectrogram", "scalogram")

    if is_tf and not panel.get("stacked"):
        ax.set_ylabel("Frequency (Hz)", fontsize=S.label_pt, color=INK)
        if panel.get("log_freq"):
            ax.set_yscale("log")
            ax.set_ylim(extent[2], extent[3])
        ch = panel.get("channel") or {}
        if ch and not (spec.get("title") or "").strip():
            ax.set_title("%s  %s" % (ch.get("label", ""), panel.get("method", "")),
                         fontsize=S.panel_title_pt, color=INK, loc="left", pad=5)
    else:
        ax.set_ylabel("Channel", fontsize=S.label_pt, color=INK)
        if rows:
            lab_in = S.pt(S.chan_pt) * 1.5
            max_labels = max(2, int((ax.figure.get_size_inches()[1] * 0.6) / lab_in))
            stride = max(1, int(np.ceil(len(rows) / max_labels)))
            # The image is drawn origin="upper", so rows[0] sits at the TOP of
            # the extent. Ticks therefore descend, or labels mirror the data.
            ticks = np.linspace(extent[3] - 0.5, extent[2] + 0.5, len(rows))
            ax.set_yticks(ticks)
            ax.set_yticklabels(
                [(r["label"] + (" (bad)" if r.get("bad") else ""))
                 if (i % stride == 0) else ""
                 for i, r in enumerate(rows)], fontsize=S.chan_pt)

    if spec.get("grid", True):
        _raster_grid(ax, extent, rows, is_tf and not panel.get("stacked"), S)

    _draw_events(ax, spec, extent[0], extent[1])

    if spec.get("colorbar", True):
        _add_colorbar(ax, panel, S)


def _raster_grid(ax, extent, rows, freq_axis, S):
    """Thin time and channel grid over a raster.

    Drawn ON TOP of the image (the image is zorder 1) at low alpha, so it reads
    as a ruler rather than competing with the data.
    """
    ax.xaxis.set_major_locator(MaxNLocator(nbins=max(4, int(6 * S.k)),
                                           steps=[1, 2, 2.5, 5, 10]))
    for x in ax.get_xticks():
        if extent[0] <= x <= extent[1]:
            ax.axvline(x, color=GRID, linewidth=0.4, alpha=0.55, zorder=3)

    if freq_axis or not rows:
        for y in ax.get_yticks():
            if extent[2] <= y <= extent[3]:
                ax.axhline(y, color=GRID, linewidth=0.4, alpha=0.45, zorder=3)
        return

    # One line per channel boundary, thinned so dense probes stay readable.
    n = len(rows)
    stride = 1 if n <= 34 else int(np.ceil(n / 34.0))
    for i in range(1, n):
        if i % stride:
            continue
        y = extent[3] - i
        ax.axhline(y, color=GRID, linewidth=0.35, alpha=0.42, zorder=3)


def _add_colorbar(ax, panel, S=None):
    import matplotlib.colors as mcolors
    from mpl_toolkits.axes_grid1 import make_axes_locatable
    div = make_axes_locatable(ax)
    cax = div.append_axes("right", size="2.4%", pad=0.05)
    norm = mcolors.Normalize(vmin=panel["clim"][0], vmax=panel["clim"][1])
    sm = plt.cm.ScalarMappable(norm=norm, cmap=analysis.get_cmap(panel["cmap"]))
    cb = plt.colorbar(sm, cax=cax)
    S = S or _Scale(11.0, 8.5)
    cb.ax.tick_params(labelsize=S.small_pt, colors=MUTED)
    cb.outline.set_edgecolor(GRID)
    # Units go horizontally above the bar. A rotated axis label here collides
    # with the neighbouring panel's y-label in a tight grid.
    cax.set_title(panel.get("units", ""), fontsize=S.small_pt, color=MUTED, pad=3)


def _draw_events(ax, spec, t0, t1):
    events = spec.get("events") or []
    if not events:
        return
    shown = 0
    for ev in events:
        start = ev.get("start") if isinstance(ev, dict) else ev
        if start is None or not (t0 <= start <= t1):
            continue
        end = ev.get("end") if isinstance(ev, dict) else None
        if end is not None and end > start:
            ax.axvspan(start, min(end, t1), color=EVENT, alpha=0.13,
                       linewidth=0, zorder=1)
        ax.axvline(start, color=EVENT, linewidth=0.7, alpha=0.6,
                   dashes=(3, 2), zorder=4)
        shown += 1
        if shown > 800:          # a dense detector run would swamp the axes
            break


def _decode_data_uri(uri):
    import base64
    raw = base64.b64decode(uri.split(",", 1)[1])
    from matplotlib.image import imread
    return imread(io.BytesIO(raw), format="png")


def _draw_metadata(fig, layout, sessions, S=None):
    """The provenance strip along the bottom."""
    meta = layout.get("metadata") or {}
    sess = sessions.get(layout.get("primary_session") or "default") or \
        (list(sessions.values())[0] if sessions else None)

    left, right = [], []

    who = meta.get("author") or ""
    when = meta.get("date") or datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    if who:
        left.append("Generated by %s" % who)
    left.append(when)
    if meta.get("machine"):
        left.append(meta["machine"])

    if sess:
        right.append(sess.get("name", ""))
        if layout.get("session_label"):
            right.insert(0, layout["session_label"])
        right.append("%.0f Hz" % (sess.get("fs") or 0))
    filt = []
    for key, tag in (("highpass", "HP"), ("lowpass", "LP"), ("notch", "notch")):
        v = layout.get(key)
        if v:
            filt.append("%s %g" % (tag, float(v)))
    if filt:
        right.append(" / ".join(filt) + " Hz")
    if layout.get("t0") is not None and layout.get("t1") is not None:
        right.append("%.3f-%.3f s" % (float(layout["t0"]), float(layout["t1"])))

    line1 = "  ·  ".join(x for x in left if x)
    line2 = "  ·  ".join(str(x) for x in right if x)

    S = S or _Scale(*fig.get_size_inches())
    h = float(fig.get_size_inches()[1])
    # The footer is sized in points, not as a fixed fraction of the page, so a
    # 3in figure gets a proportionally shorter band instead of one that eats
    # half the plot.
    band = (S.pt(S.meta_pt) * 2 + 0.10) / h

    fig.patches.append(plt.Rectangle(
        (0.0, 0.0), 1.0, band, transform=fig.transFigure,
        facecolor="#f4f7f5", edgecolor="none", zorder=0))
    fig.patches.append(plt.Rectangle(
        (0.0, band), 1.0, min(0.004, 0.02 / h), transform=fig.transFigure,
        facecolor=UVM_GOLD, edgecolor="none", zorder=1))

    # Roughly how many characters fit before the right-hand provenance block
    # begins. A fixed length runs straight through it on a narrow page.
    cap = max(24, int((fig.get_size_inches()[0] * 0.56) / (S.pt(S.meta_pt) * 0.56)))
    fig.text(0.012, band * 0.64, _clip(line2, cap), fontsize=S.meta_pt,
             color=INK, va="center", ha="left")
    fig.text(0.012, band * 0.24, _clip(line1, cap), fontsize=S.small_pt,
             color=MUTED, va="center", ha="left")

    tail = []
    if meta.get("source_path"):
        tail.append(_shorten(meta["source_path"], 78))
    if meta.get("run_id"):
        tail.append("log " + meta["run_id"])
    if meta.get("notes"):
        tail.append(meta["notes"])
    # On a narrow page there is simply no room for a right-hand block, and
    # forcing one in is what made the footer overlap itself.
    if tail and fig.get_size_inches()[0] >= 5.0:
        fig.text(0.988, band * 0.45, "\n".join(_clip(t, cap) for t in tail[:2]),
                 fontsize=max(4.5, S.small_pt - 0.5), color=MUTED,
                 va="center", ha="right", linespacing=1.5)


def _clip(text, n):
    """Truncate with an ellipsis so footer blocks cannot collide."""
    text = str(text)
    return text if len(text) <= n else text[:max(1, n - 1)] + "…"


def _shorten(path, n):
    path = str(path)
    if len(path) <= n:
        return path
    return path[:n // 2 - 2] + "..." + path[-(n // 2 - 1):]
