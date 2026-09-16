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

from . import analysis, csc, probes

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

    # What the footer will come to, worked out before the grid is laid out
    # so the reservation is the real number rather than three lines' worth.
    # A letter page comes to three; a 3.5in column comes to five, and it
    # fitted only because the space under the x-axis labels happened to be
    # free.
    meta_plan = (_meta_plan(layout, sessions, width, height, S)
                 if show_meta else None)
    meta_in = _meta_inches(meta_plan) if meta_plan else 0.0
    title_in = 0.0
    if title:
        title_in += S.pt(S.title_pt) * 1.35
    if subtitle:
        title_in += S.pt(S.sub_pt) * 1.5

    fig = plt.figure(figsize=(width, height), dpi=dpi)
    fig.patch.set_facecolor("white")

    left_in = _left_margin(layout, sessions, S)
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
        _draw_metadata(fig, layout, sessions, S, meta_plan)

    buf = io.BytesIO()
    save_kw = {"format": fmt, "facecolor": "white"}
    if fmt == "png":
        save_kw["dpi"] = dpi
    fig.savefig(buf, **save_kw)
    plt.close(fig)
    return buf.getvalue(), problems


def _left_margin(layout, sessions, S):
    """Room for the y tick labels, measured from the labels.

    It was a flat four-and-a-bit characters' worth, which fits "CSC5" and
    cuts "CSC59 (bad)" -- and a bad channel is exactly the row somebody goes
    looking for. Channel labels are known before anything is drawn, so the
    margin is taken from the longest one that will be drawn.
    """
    flat = S.pt(S.tick_pt) * 4.2 + 0.22
    try:
        chans = None
        for sess in (sessions or {}).values():
            got = (sess or {}).get("channels") or []
            if got:
                chans = got
                break
        if not chans:
            return flat
        keep = layout.get("channels")
        if keep:
            idx = set()
            for i in keep:
                try:
                    idx.add(int(i))
                except (TypeError, ValueError):
                    continue
            rows = [c for i, c in enumerate(chans) if i in idx] or chans
        else:
            rows = chans
        widest = max(len(str(c.get("label") or "")) for c in rows)
        # " (bad)" is appended by every panel that draws a bad row.
        bad = set()
        for b in (layout.get("bad_channels") or []):
            try:
                bad.add(int(b))
            except (TypeError, ValueError):
                continue
        if bad and any(int(c.get("number", -1)) in bad or c.get("bad")
                       for c in rows):
            widest += len(" (bad)")
        # 0.56 em per character, the same average the footer's cap uses.
        want = widest * S.pt(S.tick_pt) * 0.56 + 0.14
        return max(flat, min(want, 1.1))
    except Exception:                                          # noqa: BLE001
        # A margin is not worth failing a figure over.
        return flat


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
    sess = _session_for(p, sessions)
    S = S or _Scale(11.0, 8.5, layout)
    spec = dict(p)
    spec.setdefault("t0", layout.get("t0", 0))
    spec.setdefault("t1", layout.get("t1", 10))
    for key in ("highpass", "lowpass", "notch", "channels", "bad_channels",
                "spacing_um", "cmap"):
        if key not in spec and key in layout:
            spec[key] = layout[key]

    # A probe view is one panel that subdivides itself. Asked for by name, so
    # nothing else changes shape by surprise.
    if spec.get("probe_view") and spec.get("probe"):
        first = _draw_probe_panel(fig, gs, p, sess, spec, rows, cols,
                                  layout, S)
        ttl = (p.get("title") or "").strip()
        if ttl and first is not None:
            first.set_title(
                ttl, fontsize=S.panel_title_pt, color=INK, loc="left",
                pad=max(2.0, S.pt(S.panel_title_pt) * 40), weight="bold")
        return

    ax = fig.add_subplot(_slot(gs, p, rows, cols))

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


def _probe_columns(sess, spec):
    """This probe's columns, in the order they sit on the probe.

    By shank and then by physical x, so the panel reads left to right across
    the actual instrument: back shank left/centre/right, then front. The pane
    grid in the viewer uses the probe figure's own order (centre first, being
    the column with the tip contact); a figure of the probe uses the probe's.

    Columns with nothing in them are dropped rather than drawn empty -- a
    recording with a different montage should show fewer columns, not six
    boxes of which two are blank.
    """
    cols = probes.columns_for(spec.get("probe"), sess.get("channels") or [])
    if not cols:
        return None
    keep = spec.get("channels")
    allow = set(int(i) for i in keep) if keep else None
    out = []
    for c in cols:
        idx = [int(i) for i in (c.get("indices") or [])
               if allow is None or int(i) in allow]
        if idx:
            out.append(dict(c, indices=idx))
    if not out:
        return None

    # Which columns, and in what order.
    #
    # `probe_columns` is a list of column ids ("W3", "W1", ...). It is how
    # the other half of the request -- "remove certain windows and arrange
    # certain windows in certain order" -- survives the six panes being
    # collapsed into one panel. A shank that broke mid-experiment is three
    # columns of noise beside three of data, sharing one colour scale, so
    # dropping it makes the rest readable and not merely tidier.
    #
    # Ids the recording has nothing for are skipped rather than drawn empty,
    # and an order naming nothing at all falls back to the probe's own --
    # a figure with no columns is not what anybody meant.
    want = spec.get("probe_columns")
    if want:
        by_id = {str(c.get("id")): c for c in out}
        picked = [by_id[str(w)] for w in want if str(w) in by_id]
        if len(picked) >= 1:
            return picked

    rank = {"back": 0, "front": 1}
    out.sort(key=lambda c: (rank.get(c.get("shank"), 9),
                            float(c.get("x_um") or 0)))
    return out


def _csc_span(col):
    """The channel numbers in this column, said in the shortest true way.

    "Which window is which" is the question a six-column panel has to answer
    on its face, and the answer is the CSC numbers. A column is every third
    channel, so the regular ones are given as a range with their step --
    listing eleven numbers under a column an inch wide fits nowhere.
    """
    got = sorted(int(n) for n in (col.get("csc_present")
                                  or col.get("csc") or []))
    if not got:
        return ""
    def run(seq):
        """Is `seq` an even run, and of what step?"""
        if len(seq) < 3:
            return None
        step = seq[1] - seq[0]
        if step > 0 and all(b - a == step for a, b in zip(seq, seq[1:])):
            return step
        return None

    step = run(got)
    if step:
        return "CSC %d-%d/%d" % (got[0], got[-1], step)
    # The two centre columns are an even run plus the tip contact, so the
    # run breaks at the last number only. Said as "1-31/3 +32", because
    # "CSC 1-32" would claim thirty-two channels where there are twelve.
    step = run(got[:-1])
    if step:
        return "CSC %d-%d/%d +%d" % (got[0], got[-2], step, got[-1])
    if len(got) > 4:
        return "CSC %d-%d (%d)" % (got[0], got[-1], len(got))
    return "CSC " + ",".join(str(n) for n in got)


def _shared_scale(sess, spec, columns, kind):
    """One scale for every column, worked out before any is drawn.

    Six columns of one recording each scaled to itself are six pictures that
    cannot be compared, which is the only reason to put them side by side. A
    scale the user has pinned is left exactly alone.
    """
    if kind == "traces":
        if spec.get("ylim"):
            return {}
        best = 0.0
        for col in columns:
            try:
                win = csc.get_window(
                    sess, spec.get("t0", 0), spec.get("t1", 10),
                    channels=col["indices"], px=600,
                    highpass=float(spec.get("highpass", 0) or 0),
                    lowpass=float(spec.get("lowpass", 0) or 0),
                    notch=float(spec.get("notch", 0) or 0),
                    mode="voltage",
                    spacing_um=float(spec.get("spacing_um", 50) or 50))
            except Exception:                                  # noqa: BLE001
                continue
            if win.get("ok"):
                best = max(best, float(win.get("robust_auto") or 0))
        return {"ylim": best} if best > 0 else {}

    if analysis._explicit_clim(spec) is not None:
        return {}
    lo = hi = None
    for col in columns:
        sub = dict(spec)
        sub["channels"] = col["indices"]
        sub["px"] = 700
        try:
            got = analysis.render_panel(sess, sub)
        except Exception:                                      # noqa: BLE001
            continue
        span = got.get("clim_auto") or got.get("clim")
        if not span or len(span) != 2:
            continue
        lo = float(span[0]) if lo is None else min(lo, float(span[0]))
        hi = float(span[1]) if hi is None else max(hi, float(span[1]))
    if lo is None or hi is None or hi <= lo:
        return {}
    # Symmetric for the signed maps: zero has to stay the middle colour or a
    # sink reads as a source.
    if lo < 0 < hi:
        edge = max(abs(lo), abs(hi))
        lo, hi = -edge, edge
    return {"clim": [lo, hi]}


def _thin_yticks(ax, keep=3):
    """Keep a few channel labels, not all of them.

    A column an inch wide cannot carry eleven "CSC 12 (bad)" labels, and six
    of those columns is a wall of text where the data should be. The ends are
    always kept: they are what says which way up a column is.
    """
    ticks = ax.get_yticklabels()
    if not ticks:
        return
    size = ticks[0].get_fontsize()
    labs = [t.get_text() for t in ticks]
    filled = [i for i, t in enumerate(labs) if t.strip()]
    if len(filled) <= keep:
        return
    want = {filled[0], filled[-1]}
    step = max(1, len(filled) // max(1, keep - 1))
    for i in range(0, len(filled), step):
        if len(want) >= keep:
            break
        want.add(filled[i])
    ax.set_yticklabels([t if i in want else "" for i, t in enumerate(labs)],
                       fontsize=size)


def _draw_probe_panel(fig, gs, p, sess, spec, rows, cols, layout, S):
    """The whole probe in one cell: its columns side by side as they sit.

    The cell is subdivided rather than the figure being given more cells, so
    the panel stays one panel -- 1x1, movable, spannable, one title -- and the
    grid the user arranged is the grid they get.
    """
    from matplotlib.gridspec import GridSpecFromSubplotSpec

    columns = _probe_columns(sess, spec)
    if not columns:
        raise ComposeError(
            "None of this probe's channels are in that recording, so there "
            "are no columns to draw.")

    kind = spec.get("panel", "traces")
    shared = _shared_scale(sess, spec, columns, kind)
    # One column picked is a legitimate panel -- the same view an H3 gives --
    # and the gap and the shared scale both have to survive it.
    single = len(columns) == 1

    # A gap between the shanks: they sit 113 um apart, and two shanks read as
    # two things rather than as six equal columns.
    widths = []
    where = []
    for i, c in enumerate(columns):
        if i and c.get("shank") != columns[i - 1].get("shank"):
            widths.append(0.30)
            where.append(None)
        widths.append(1.0)
        where.append(i)

    # Room for the channel labels between the columns. At 0.10 each column's
    # labels were drawn inside its left neighbour's data.
    inner = GridSpecFromSubplotSpec(
        1, len(widths), subplot_spec=_slot(gs, p, rows, cols),
        width_ratios=widths, wspace=0.42)

    drawn = []
    last = None
    for slot, ci in enumerate(where):
        if ci is None:
            continue
        col = columns[ci]
        sub = dict(spec)
        sub["channels"] = col["indices"]
        sub["colorbar"] = False
        for gone in ("title", "probe", "probe_view"):
            sub.pop(gone, None)
        for k, v in shared.items():
            sub[k] = v

        # No lane note inside the columns. It is one number for all six, and
        # right-aligned in an axes an inch wide it ran through two of the
        # heads. It goes on the panel instead, below.
        sub["show_scale"] = False

        ax = fig.add_subplot(inner[0, slot])
        if kind == "traces":
            _draw_traces(ax, sess, sub, layout, S)
        else:
            last = _draw_image_panel(ax, sess, sub, S) or last

        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(labelsize=S.tick_pt, colors=MUTED)

        # Which column this is, and which channels are in it -- inside the
        # axes, because `set_title` belongs to the panel and printing both
        # there put "csd - all six columns" over "W1 centre".
        head = ("%s %s" % (col.get("id") or "",
                           col.get("column") or "")).strip()
        ax.text(0.03, 0.995, head + "\n" + _csc_span(col),
                transform=ax.transAxes, fontsize=S.small_pt, color=INK,
                ha="left", va="top", zorder=7,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.82,
                          pad=1.4))

        # Three time labels at most, and never at the very edges: a column an
        # inch wide put its last label against its neighbour's first, which
        # read as "4.02.0".
        ax.xaxis.set_major_locator(MaxNLocator(
            nbins=3 if len(columns) > 2 else 6,
            prune="upper" if len(columns) > 1 else None,
            steps=[1, 2, 2.5, 5, 10]))
        _thin_yticks(ax)
        drawn.append(ax)

    # One time axis label and one channel axis label for the panel. Six of
    # each is six times the ink for one fact.
    for i, ax in enumerate(drawn):
        if i:
            ax.set_ylabel("")
        if i != len(drawn) // 2:
            ax.set_xlabel("")

    if last is not None and spec.get("colorbar", True) and drawn:
        _add_colorbar(drawn[-1], last, S)
    if single and drawn:
        # Nothing to compare it against, so the head is the panel's title's
        # job rather than a column label competing with it.
        for t in drawn[0].texts:
            if t.get_zorder() == 7:
                t.set_visible(False)

    # What the columns are drawn to, said once, on the line the panel title
    # sits on. For a raster the shared colorbar already says it.
    if kind == "traces" and shared.get("ylim") and drawn:
        gain = float(spec.get("gain", 1.0) or 1.0)
        lane = float(shared["ylim"]) * 2.0 / (gain or 1.0)
        box = drawn[-1].get_position()
        top = max(a.get_position().y1 for a in drawn)
        fig.text(box.x1, top + (S.pt(S.small_pt) * 0.9)
                 / float(fig.get_size_inches()[1]),
                 "lane %.3g uV \u00b7 one scale across all %d columns"
                 % (lane, len(drawn)),
                 fontsize=S.small_pt, color=MUTED, ha="right", va="bottom")

    return drawn[0] if drawn else None


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
        # Where the scale came from, in the caller's words when it has any.
        # A probe panel computes one scale across its columns and hands it to
        # each of them, and a column cannot tell that from a user's pin -- so
        # it printed "pinned" six times while the footer said "auto".
        note = spec.get("scale_note")
        if note is None:
            note = ", pinned" if win.get("ylim_manual") else ""
        # Inside the axes, top-right. Above the axes it fights the panel title
        # once the page gets small.
        ax.text(0.995, 0.985, "lane %.3g uV%s" % (lane, note),
                transform=ax.transAxes, fontsize=S.small_pt, color=MUTED,
                ha="right", va="top", zorder=6,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.75,
                          pad=1.2))


def _draw_image_panel(ax, sess, spec, S=None):
    """Draw a rendered raster into `ax`, and hand back what was drawn.

    Returned so a caller drawing several can put one colorbar on the lot --
    the columns of a probe share a scale, so they share a bar.
    """
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
    return panel


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


def _ranges(nums):
    """[1,2,3,7,9,10] -> "1-3, 7, 9-10"; [1,3,..,63] -> "1-63/2".

    The step matters. Every-other-channel is what "even only" gives you and
    what half of this lab records, and it has no consecutive run to collapse
    -- so thirty-two numbers printed in full and ran off a journal-column
    page. The JS side already says `CSC 1-10/3` for a probe column; this is
    the same rule, so a figure and the builder agree.
    """
    got = sorted({int(n) for n in nums})
    if not got:
        return ""
    if len(got) > 3:
        step = got[1] - got[0]
        if step > 1 and all(b - a == step for a, b in zip(got, got[1:])):
            return "%d-%d/%d" % (got[0], got[-1], step)
    out = []
    run = [got[0]]
    for n in got[1:]:
        if n == run[-1] + 1:
            run.append(n)
            continue
        out.append(run)
        run = [n]
    out.append(run)
    return ", ".join("%d-%d" % (r[0], r[-1]) if len(r) > 1 else str(r[0])
                     for r in out)


def _numbers_for(sess, indices):
    """Channel NUMBERS for a list of indices into the session's channels.

    The layout carries indices, because that is what the panels take. A
    reader wants the numbers on the front of the amplifier.
    """
    chans = (sess or {}).get("channels") or []
    out = []
    for i in indices or []:
        try:
            i = int(i)
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(chans):
            num = chans[i].get("number")
            if num is not None:
                out.append(int(num))
    return out


def _scale_note(layout, panels):
    """Whether the scale was pinned or worked out, and to what.

    A printed raster with an auto scale cannot be compared against another
    printed raster, and nothing on the page said which it was.
    """
    kinds = {p.get("panel", "traces") for p in panels}
    notes = []
    clim = None
    for p in panels:
        if p.get("clim") and len(p["clim"]) == 2:
            clim = p["clim"]
            break
    if clim is None and layout.get("clim") and len(layout["clim"]) == 2:
        clim = layout["clim"]
    if kinds - {"traces"}:
        if clim:
            notes.append("colour pinned %.3g to %.3g" % (float(clim[0]),
                                                         float(clim[1])))
        else:
            notes.append("colour auto (99.5th pct)")
    if "traces" in kinds:
        ylim = None
        for p in panels:
            if p.get("ylim"):
                ylim = p["ylim"]
                break
        if ylim is None and layout.get("ylim"):
            ylim = layout["ylim"]
        notes.append("amplitude pinned %.3g uV" % float(ylim) if ylim
                     else "amplitude auto")
    # A probe panel derives one scale and applies it to every column, which is
    # neither a pin nor six independent autos -- and it is the fact that makes
    # the columns comparable, so it is said rather than left to be assumed.
    for p in panels:
        if not p.get("probe_view"):
            continue
        picked = p.get("probe_columns") or []
        notes.append("one scale across " + (
            "%d columns" % len(picked) if len(picked) > 1
            else ("the one column drawn" if len(picked) == 1
                  else "all the probe's columns")))
        break
    return notes


def _pack(parts, cap):
    """Lay short phrases into lines of at most `cap` characters.

    Not truncation. Everything given is printed; the only question is which
    line it lands on. The footer used to drop whatever came after a
    character count, which for "which channels were used" meant printing
    half an answer -- worse than printing none.
    """
    sep = "  \u00b7  "
    lines = []
    cur = ""
    for raw in parts:
        for bit in _fit(str(raw).strip(), cap):
            if not bit:
                continue
            if not cur:
                cur = bit
            elif len(cur) + len(sep) + len(bit) <= cap:
                cur += sep + bit
            else:
                lines.append(cur)
                cur = bit
    if cur:
        lines.append(cur)
    return lines


def _fit(bit, cap):
    """One phrase as one or more pieces, none longer than `cap` if avoidable.

    `_pack` lays whole phrases onto lines and never split one, so a phrase
    longer than the line ran off the page -- measured at the 3.5in preset,
    where the channel list was cut by the paper edge. Cutting is what this
    footer was rewritten to stop doing, so it breaks the phrase instead: at
    its own ", " separators first, because that is where it reads naturally,
    then at spaces.

    A single unsplittable word wider than the page is returned whole. There
    is nothing to do about that but let it stick out, and pretending
    otherwise would mean cutting it.
    """
    if len(bit) <= cap:
        return [bit]
    for at in (", ", " "):
        parts = bit.split(at)
        if len(parts) < 2:
            continue
        out, cur = [], ""
        for piece in parts:
            add = piece if not cur else cur + at.rstrip() + " " + piece
            if len(add) <= cap or not cur:
                cur = add
            else:
                out.append(cur)
                cur = piece
        if cur:
            out.append(cur)
        if all(len(o) <= cap for o in out) or at == " ":
            return out
    return [bit]


def _meta_plan(layout, sessions, width, height, S):
    """The footer's lines and their point size, before anything is drawn.

    Split out of `_draw_metadata` because the grid is laid out first and has
    to know how much room the band will want. It used to reserve three
    lines, which is what a letter page comes to; a 3.5in column came to five
    and fitted only because the space under the x-axis labels happened to be
    free.
    """
    meta = layout.get("metadata") or {}
    sess = sessions.get(layout.get("primary_session") or "default") or \
        (list(sessions.values())[0] if sessions else None)
    panels = layout.get("panels") or []

    # ---- what was recorded
    what = []
    if layout.get("session_label"):
        what.append(str(layout["session_label"]))
    if sess and sess.get("name"):
        what.append(str(sess["name"]))
    ident = layout.get("identity") or {}
    hemi = (meta.get("hemisphere") or ident.get("hemisphere") or "")
    if hemi:
        # Said in full: "L" in a corner is the kind of thing that gets read
        # the wrong way round a year later.
        pretty = {"l": "left", "r": "right", "left": "left",
                  "right": "right", "b": "both", "both": "both"}
        what.append("%s hemisphere" % pretty.get(str(hemi).strip().lower(),
                                                 str(hemi)))
    probe_id = None
    for p in panels:
        if p.get("probe"):
            probe_id = p["probe"]
            break
    probe_id = probe_id or layout.get("probe")
    if probe_id:
        got = probes.get(probe_id)
        what.append((got or {}).get("name") or str(probe_id).upper())
    if sess and sess.get("fs"):
        what.append("%.0f Hz" % float(sess["fs"]))
    if layout.get("t0") is not None and layout.get("t1") is not None:
        t0, t1 = float(layout["t0"]), float(layout["t1"])
        what.append("%.3f-%.3f s (%.3f s)" % (t0, t1, max(0.0, t1 - t0)))

    # ---- what was drawn from it
    how = []
    filt = []
    for key, tag in (("highpass", "HP"), ("lowpass", "LP"),
                     ("notch", "notch")):
        v = layout.get(key)
        if v:
            filt.append("%s %g" % (tag, float(v)))
    how.append(" / ".join(filt) + " Hz" if filt else "unfiltered")

    total = len((sess or {}).get("channels") or [])
    nums = _numbers_for(sess, layout.get("channels"))
    if nums and total and len(nums) == total:
        how.append("all %d channels" % total)
    elif nums:
        how.append("%d of %d channels: CSC %s"
                   % (len(nums), total, _ranges(nums)))
    bad = [int(b) for b in (layout.get("bad_channels") or [])]
    how.append("bad CSC " + _ranges(bad) if bad else "no channels marked bad")
    if layout.get("spacing_um"):
        how.append("%g um spacing" % float(layout["spacing_um"]))
    if layout.get("gain") and float(layout["gain"]) != 1.0:
        how.append("gain x%g" % float(layout["gain"]))
    how.extend(_scale_note(layout, panels))
    if len(panels) > 1:
        how.append("%d panels" % len(panels))

    # ---- who drew it
    who = []
    if meta.get("author"):
        who.append("Generated by %s" % meta["author"])
    who.append(meta.get("date")
               or datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"))
    if meta.get("machine"):
        who.append(str(meta["machine"]))
    if meta.get("source_path"):
        who.append(str(meta["source_path"]))
    if meta.get("run_id"):
        who.append("log " + str(meta["run_id"]))
    if meta.get("notes"):
        who.append(str(meta["notes"]))

    w, h = float(width), float(height)

    # How many characters fit across the page at this size. 0.56 em per
    # character is the average for this face and is what the old cap used.
    def cap_at(pt):
        return max(28, int((w - 0.20) / (_Scale.pt(pt) * 0.56)))

    # Shrink the type a little before adding a line, then let it grow lines.
    # A page that cannot hold this in four lines is a page too small for a
    # provenance strip at all, and the note is dropped to the plot's benefit.
    lines = []
    pt = S.meta_pt
    for _ in range(4):
        cap = cap_at(pt)
        lines = _pack(what, cap) + _pack(how, cap) + _pack(who, cap)
        if len(lines) <= 3:
            break
        pt = max(4.2, pt * 0.88)
    return {"lines": lines, "pt": pt}


def _meta_inches(plan):
    """How tall the band will be, in inches. The same arithmetic the band
    itself uses, so the reservation and the drawing cannot disagree."""
    n = max(1, len(plan["lines"]))
    return _Scale.pt(plan["pt"]) * (n + 0.9) + 0.06


def _draw_metadata(fig, layout, sessions, S=None, plan=None):
    """The provenance strip along the bottom.

    Three groups, in the order a reader needs them: what was recorded, what
    was drawn from it, and who drew it. `plan` is what `render_figure`
    already worked out to reserve the space; recomputed here only when
    something calls this directly.
    """
    S = S or _Scale(*fig.get_size_inches())
    w, h = fig.get_size_inches()
    plan = plan or _meta_plan(layout, sessions, w, h, S)
    lines, pt = plan["lines"], plan["pt"]
    n = max(1, len(lines))

    band = _meta_inches(plan) / h
    fig.patches.append(plt.Rectangle(
        (0.0, 0.0), 1.0, band, transform=fig.transFigure,
        facecolor="#f4f7f5", edgecolor="none", zorder=0))
    fig.patches.append(plt.Rectangle(
        (0.0, band), 1.0, min(0.004, 0.02 / h), transform=fig.transFigure,
        facecolor=UVM_GOLD, edgecolor="none", zorder=1))

    # Laid out from the top of the band down, so adding a line pushes into
    # the space the band already grew by rather than off the page.
    step = _Scale.pt(pt) * 1.16 / h
    y = band - step * 0.72
    for i, line in enumerate(lines):
        fig.text(0.010, y, line, fontsize=pt,
                 color=INK if i == 0 else MUTED, va="center", ha="left")
        y -= step


def _clip(text, n):
    """Truncate with an ellipsis so footer blocks cannot collide."""
    text = str(text)
    return text if len(text) <= n else text[:max(1, n - 1)] + "…"


def _shorten(path, n):
    path = str(path)
    if len(path) <= n:
        return path
    return path[:n // 2 - 2] + "..." + path[-(n // 2 - 1):]
